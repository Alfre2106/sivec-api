"""Servicio de reservas: reservar, cancelar y expirar.

La concurrencia se resuelve SIEMPRE con bloqueo de filas en la base de datos
(`with_for_update()`), nunca con locks de Python. Todas las operaciones de
escritura ocurren dentro de una única transacción.
"""

from datetime import timedelta

from flask import current_app

from app.extensions import db
from app.models.asiento_funcion import AsientoFuncion
from app.models.reserva import Reserva
from app.models.enums import EstadoAsiento, EstadoReserva
from app.services.auditoria_service import registrar_auditoria
from app.services.funciones_service import obtener_funcion
from app.utils.errores import ErrorAPI
from app.utils.funciones_tiempo import estado_efectivo, funcion_ya_inicio
from app.models.enums import EstadoFuncion
from app.utils.tiempo import ahora_utc


# --- Expiración perezosa (sin escribir) -----------------------------------

def reserva_vencida(reserva: Reserva, ahora=None) -> bool:
    """True si una reserva activa ya venció (vence_en < ahora)."""
    ahora = ahora or ahora_utc()
    return (reserva.estado == EstadoReserva.ACTIVA
            and reserva.vence_en is not None
            and reserva.vence_en < ahora)


def estado_asiento_efectivo(asiento: AsientoFuncion, ahora=None) -> EstadoAsiento:
    """Calcula el estado EFECTIVO de un asiento SIN escribir en la base.

    Un asiento 'reservado' cuya reserva activa ya venció se reporta como
    'disponible'. El estado real se corrige en escritura o en el scheduler.
    """
    if asiento.estado != EstadoAsiento.RESERVADO:
        return asiento.estado
    ahora = ahora or ahora_utc()
    # ¿Tiene alguna reserva activa aún vigente?
    hay_vigente = any(
        r.estado == EstadoReserva.ACTIVA
        and r.vence_en is not None and r.vence_en >= ahora
        for r in asiento.reservas
    )
    return EstadoAsiento.RESERVADO if hay_vigente else EstadoAsiento.DISPONIBLE


# --- Expiración con escritura (para reservar y para el scheduler) ---------

def _expirar_reservas_de_asientos(asiento_ids: list[int], ahora=None) -> int:
    """Expira, dentro de la transacción actual, las reservas vencidas de los
    asientos indicados y devuelve esos asientos a disponible.

    Se usa dentro de `reservar` tras bloquear las filas. No hace commit.
    Devuelve cuántas reservas se expiraron.
    """
    if not asiento_ids:
        return 0
    ahora = ahora or ahora_utc()
    vencidas = (Reserva.query
                .filter(Reserva.asiento_id.in_(asiento_ids),
                        Reserva.estado == EstadoReserva.ACTIVA,
                        Reserva.vence_en < ahora)
                .all())
    for reserva in vencidas:
        reserva.estado = EstadoReserva.EXPIRADA
        asiento = db.session.get(AsientoFuncion, reserva.asiento_id)
        if asiento and asiento.estado == EstadoAsiento.RESERVADO:
            asiento.estado = EstadoAsiento.DISPONIBLE
    return len(vencidas)


def expirar_reservas_vencidas() -> int:
    """Expira todas las reservas vencidas del sistema (job del scheduler).

    Usa SELECT ... FOR UPDATE SKIP LOCKED para no interferir con transacciones
    en curso: las filas bloqueadas por otra operación se omiten y se tratarán
    en la siguiente corrida. Devuelve cuántas reservas se liberaron.
    """
    ahora = ahora_utc()

    # Bloqueamos solo las reservas vencidas que no estén siendo tocadas.
    vencidas = (Reserva.query
                .filter(Reserva.estado == EstadoReserva.ACTIVA,
                        Reserva.vence_en < ahora)
                .order_by(Reserva.id)
                .with_for_update(skip_locked=True)
                .all())

    if not vencidas:
        return 0

    asiento_ids = [r.asiento_id for r in vencidas]
    for reserva in vencidas:
        reserva.estado = EstadoReserva.EXPIRADA

    # Devolvemos a disponible los asientos reservados cuyas reservas expiramos.
    asientos = (AsientoFuncion.query
                .filter(AsientoFuncion.id.in_(asiento_ids),
                        AsientoFuncion.estado == EstadoAsiento.RESERVADO)
                .with_for_update(skip_locked=True)
                .all())
    for asiento in asientos:
        asiento.estado = EstadoAsiento.DISPONIBLE

    liberadas = len(vencidas)
    # Auditoría: un solo resumen por ejecución, solo si liberó algo.
    registrar_auditoria(
        usuario_id=None, accion="expirar_reservas", entidad="reservas",
        entidad_id=None, detalle={"liberadas": liberadas})
    db.session.commit()
    return liberadas


# --- Validación del cuerpo ------------------------------------------------

def _validar_lista_asientos(datos: dict) -> list[int]:
    """Valida que 'asientos' sea una lista no vacía de enteros sin repetidos.

    Devuelve la lista de ids. Respeta el máximo por solicitud.
    """
    asientos = datos.get("asientos")
    if not isinstance(asientos, list) or len(asientos) == 0:
        raise ErrorAPI("ASIENTOS_REQUERIDOS",
                       "Debes indicar al menos un asiento.", 422)

    ids = []
    for valor in asientos:
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise ErrorAPI("ASIENTO_INVALIDO",
                           "Los ids de asiento deben ser enteros.", 422)
        ids.append(valor)

    if len(set(ids)) != len(ids):
        raise ErrorAPI("ASIENTOS_REPETIDOS",
                       "Hay asientos repetidos en la solicitud.", 422)

    maximo = current_app.config["MAX_ASIENTOS_POR_RESERVA"]
    if len(ids) > maximo:
        raise ErrorAPI(
            "DEMASIADOS_ASIENTOS",
            f"No puedes reservar más de {maximo} asientos por solicitud.", 422)
    return ids


def _validar_funcion_reservable(funcion):
    """Valida RN-08: la función existe, está activa y no ha iniciado."""
    efectivo = estado_efectivo(funcion)
    if efectivo != EstadoFuncion.ACTIVA or funcion_ya_inicio(funcion):
        raise ErrorAPI(
            "FUNCION_NO_DISPONIBLE",
            "La función no está disponible para reservar "
            "(cancelada, finalizada o ya iniciada).",
            409,
        )


# --- Reservar -------------------------------------------------------------

def reservar(datos: dict, usuario_id: int) -> dict:
    """Reserva uno o varios asientos de una función en UNA transacción.

    Pasos: validar función (RN-08), bloquear filas FOR UPDATE ordenadas por id,
    expirar vencidas, verificar disponibilidad total (todo o nada) y crear las
    reservas. Devuelve el detalle para la respuesta 201.
    """
    funcion_id = datos.get("funcion_id")
    if not isinstance(funcion_id, int) or isinstance(funcion_id, bool):
        raise ErrorAPI("FUNCION_REQUERIDA",
                       "funcion_id es obligatorio y debe ser entero.", 422)

    ids_asientos = _validar_lista_asientos(datos)

    # La función debe existir y ser reservable.
    funcion = obtener_funcion(funcion_id)
    _validar_funcion_reservable(funcion)

    try:
        # 1) Bloqueo de filas: ordenadas por id para evitar bloqueos cruzados.
        asientos = (AsientoFuncion.query
                    .filter(AsientoFuncion.id.in_(ids_asientos))
                    .order_by(AsientoFuncion.id)
                    .with_for_update()
                    .all())

        # Verificar que todos existen y pertenecen a la función.
        encontrados = {a.id for a in asientos}
        faltantes = [i for i in ids_asientos if i not in encontrados]
        ajenos = [a.id for a in asientos if a.funcion_id != funcion_id]
        if faltantes or ajenos:
            db.session.rollback()
            raise ErrorAPI(
                "ASIENTO_INVALIDO",
                "Algunos asientos no existen o no pertenecen a la función.",
                422,
                detalle={"no_encontrados": faltantes, "de_otra_funcion": ajenos},
            )

        # 2) Expirar vencidas de estos asientos dentro de la misma transacción.
        _expirar_reservas_de_asientos(ids_asientos)

        # 3) Límite de reservas activas por usuario en esta función.
        _validar_limite_por_funcion(funcion_id, usuario_id, len(ids_asientos))

        # 4) Disponibilidad total: todo o nada.
        no_disponibles = [a.id for a in asientos
                          if a.estado != EstadoAsiento.DISPONIBLE]
        if no_disponibles:
            db.session.rollback()
            raise ErrorAPI(
                "ASIENTO_NO_DISPONIBLE",
                "Uno o más asientos ya no están disponibles.",
                409,
                detalle={"asientos_no_disponibles": sorted(no_disponibles)},
            )

        # 5) Reservar: asiento -> reservado y crear fila de reserva.
        ahora = ahora_utc()
        minutos = current_app.config["RESERVA_DURACION_MINUTOS"]
        vence_en = ahora + timedelta(minutes=minutos)

        detalle_reservas = []
        for asiento in asientos:
            asiento.estado = EstadoAsiento.RESERVADO
            reserva = Reserva(
                asiento_id=asiento.id,
                usuario_id=usuario_id,
                reservado_en=ahora,
                vence_en=vence_en,
                estado=EstadoReserva.ACTIVA,
            )
            db.session.add(reserva)
            db.session.flush()
            detalle_reservas.append({
                "id": reserva.id,
                "asiento_id": asiento.id,
                "fila": asiento.fila,
                "numero": asiento.numero,
            })

        registrar_auditoria(
            usuario_id=usuario_id, accion="reservar", entidad="funciones",
            entidad_id=funcion_id,
            detalle={"asientos": [a.id for a in asientos],
                     "cantidad": len(asientos)})
        db.session.commit()
    except ErrorAPI:
        raise
    except Exception:
        db.session.rollback()
        raise

    segundos_restantes = int((vence_en - ahora_utc()).total_seconds())
    return {
        "reservas": detalle_reservas,
        "vence_en": vence_en,
        "segundos_restantes": max(0, segundos_restantes),
    }


def _validar_limite_por_funcion(funcion_id, usuario_id, cantidad_nueva):
    """Valida el máximo de reservas activas por usuario en una función.

    Cuenta las reservas activas vigentes del usuario en esa función y suma las
    nuevas; si supera el máximo, lanza 409.
    """
    maximo = current_app.config["MAX_RESERVAS_ACTIVAS_POR_FUNCION"]
    ahora = ahora_utc()
    activas = (Reserva.query
               .join(AsientoFuncion, Reserva.asiento_id == AsientoFuncion.id)
               .filter(AsientoFuncion.funcion_id == funcion_id,
                       Reserva.usuario_id == usuario_id,
                       Reserva.estado == EstadoReserva.ACTIVA,
                       Reserva.vence_en >= ahora)
               .count())
    if activas + cantidad_nueva > maximo:
        db.session.rollback()
        raise ErrorAPI(
            "LIMITE_RESERVAS",
            f"Superas el máximo de {maximo} reservas activas en esta función.",
            409,
            detalle={"activas": activas, "maximo": maximo},
        )


# --- Cancelar -------------------------------------------------------------

def cancelar_reserva(reserva_id: int, usuario_id: int) -> None:
    """Cancela una reserva propia y activa; el asiento vuelve a disponible."""
    reserva = db.session.get(Reserva, reserva_id)
    if reserva is None:
        raise ErrorAPI("RESERVA_NO_ENCONTRADA", "La reserva no existe.", 404)
    if reserva.usuario_id != usuario_id:
        raise ErrorAPI("RESERVA_AJENA",
                       "No puedes cancelar una reserva de otro usuario.", 403)
    if reserva.estado != EstadoReserva.ACTIVA:
        raise ErrorAPI("RESERVA_NO_ACTIVA",
                       "La reserva ya no está activa.", 409)

    # Bloqueamos el asiento para actualizar su estado con seguridad.
    asiento = (AsientoFuncion.query
               .filter_by(id=reserva.asiento_id)
               .with_for_update()
               .first())
    reserva.estado = EstadoReserva.CANCELADA
    if asiento and asiento.estado == EstadoAsiento.RESERVADO:
        asiento.estado = EstadoAsiento.DISPONIBLE

    registrar_auditoria(
        usuario_id=usuario_id, accion="cancelar_reserva", entidad="reservas",
        entidad_id=reserva.id, detalle={"asiento_id": reserva.asiento_id})
    db.session.commit()


def cancelar_mis_reservas_en_funcion(funcion_id: int, usuario_id: int) -> int:
    """Cancela TODAS mis reservas activas en una función. Devuelve cuántas."""
    reservas = (Reserva.query
                .join(AsientoFuncion, Reserva.asiento_id == AsientoFuncion.id)
                .filter(AsientoFuncion.funcion_id == funcion_id,
                        Reserva.usuario_id == usuario_id,
                        Reserva.estado == EstadoReserva.ACTIVA)
                .order_by(Reserva.asiento_id)
                .all())
    if not reservas:
        return 0

    asiento_ids = [r.asiento_id for r in reservas]
    asientos = (AsientoFuncion.query
                .filter(AsientoFuncion.id.in_(asiento_ids))
                .order_by(AsientoFuncion.id)
                .with_for_update()
                .all())
    mapa_asientos = {a.id: a for a in asientos}

    for reserva in reservas:
        reserva.estado = EstadoReserva.CANCELADA
        asiento = mapa_asientos.get(reserva.asiento_id)
        if asiento and asiento.estado == EstadoAsiento.RESERVADO:
            asiento.estado = EstadoAsiento.DISPONIBLE

    registrar_auditoria(
        usuario_id=usuario_id, accion="cancelar_reservas_funcion",
        entidad="funciones", entidad_id=funcion_id,
        detalle={"canceladas": len(reservas)})
    db.session.commit()
    return len(reservas)


def listar_mis_reservas(funcion_id: int, usuario_id: int) -> list[dict]:
    """Lista mis reservas activas y vigentes en una función."""
    ahora = ahora_utc()
    reservas = (Reserva.query
                .join(AsientoFuncion, Reserva.asiento_id == AsientoFuncion.id)
                .filter(AsientoFuncion.funcion_id == funcion_id,
                        Reserva.usuario_id == usuario_id,
                        Reserva.estado == EstadoReserva.ACTIVA,
                        Reserva.vence_en >= ahora)
                .order_by(AsientoFuncion.fila, AsientoFuncion.numero)
                .all())
    from app.utils.tiempo import a_iso_bogota
    resultado = []
    for r in reservas:
        asiento = db.session.get(AsientoFuncion, r.asiento_id)
        resultado.append({
            "id": r.id,
            "asiento_id": r.asiento_id,
            "fila": asiento.fila if asiento else None,
            "numero": asiento.numero if asiento else None,
            "vence_en": a_iso_bogota(r.vence_en),
            "segundos_restantes": max(
                0, int((r.vence_en - ahora).total_seconds())),
        })
    return resultado
