"""Servicio de compras: confirma la venta, simula el pago y emite entradas.

Toda la operación ocurre en UNA transacción con bloqueo de filas de los
asientos (`with_for_update()`), ordenadas por id. La concurrencia se resuelve
siempre en la base de datos, nunca con locks de Python.
"""

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.usuario import Usuario
from app.models.cliente import Cliente
from app.models.asiento_funcion import AsientoFuncion
from app.models.reserva import Reserva
from app.models.compra import Compra
from app.models.entrada import Entrada
from app.models.enums import (
    RolUsuario, EstadoAsiento, EstadoReserva, EstadoPago, EstadoEntrada,
)
from app.services.auditoria_service import registrar_auditoria
from app.services.funciones_service import obtener_funcion
from app.services.reservas_service import _validar_funcion_reservable
from app.utils.codigos import generar_codigo_entrada
from app.utils.errores import ErrorAPI
from app.utils.tiempo import ahora_utc

# Métodos de pago permitidos por rol.
METODOS_POR_ROL = {
    RolUsuario.CLIENTE: {"tarjeta"},
    RolUsuario.TAQUILLERO: {"tarjeta", "efectivo"},
}

# Número máximo de reintentos ante colisión del código único de entrada.
MAX_REINTENTOS_CODIGO = 5


# --- Resolución del cliente de la compra ----------------------------------

def _resolver_cliente(usuario: Usuario, datos: dict) -> Cliente:
    """Determina el cliente al que se asocia la compra.

    - Rol cliente: usa SIEMPRE su propio registro en `clientes` (ignora el
      bloque `cliente` del body).
    - Rol taquillero: requiere datos de cliente (al menos el nombre) y crea
      una ficha de cliente sin cuenta para la venta en taquilla.
    """
    if usuario.rol == RolUsuario.CLIENTE:
        cliente = Cliente.query.filter_by(usuario_id=usuario.id).first()
        if cliente is None:
            # Salvaguarda: todo cliente debería tener su ficha desde el registro.
            cliente = Cliente(usuario_id=usuario.id, nombre=usuario.nombre)
            db.session.add(cliente)
            db.session.flush()
        return cliente

    # Taquillero: datos del cliente obligatorios.
    datos_cliente = datos.get("cliente") or {}
    nombre = (datos_cliente.get("nombre") or "").strip()
    if not nombre:
        raise ErrorAPI(
            "CLIENTE_REQUERIDO",
            "Para una venta en taquilla debes indicar los datos del cliente "
            "(al menos el nombre).",
            422,
        )
    cliente = Cliente(
        usuario_id=None,  # venta en taquilla: cliente sin cuenta
        nombre=nombre,
        documento=(datos_cliente.get("documento") or None),
        contacto=(datos_cliente.get("contacto") or None),
    )
    db.session.add(cliente)
    db.session.flush()
    return cliente


def _validar_metodo_pago(usuario: Usuario, metodo: str) -> str:
    """Valida el método de pago según el rol."""
    metodo = (metodo or "").strip().lower()
    permitidos = METODOS_POR_ROL.get(usuario.rol, set())
    if metodo not in permitidos:
        raise ErrorAPI(
            "METODO_PAGO_INVALIDO",
            f"Método de pago no válido. Permitidos para tu rol: "
            f"{', '.join(sorted(permitidos))}.",
            422,
        )
    return metodo


def _resolver_asientos_objetivo(funcion_id, datos, usuario_id):
    """Devuelve la lista de ids de asiento a comprar.

    Si el body trae `asientos`, se valida (lista no vacía de enteros sin
    repetidos). Si se omite, se usan TODAS mis reservas activas y vigentes en
    la función.
    """
    if "asientos" in datos and datos["asientos"] is not None:
        asientos = datos["asientos"]
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
        return ids

    # Sin lista: usar mis reservas activas vigentes en la función.
    ahora = ahora_utc()
    reservas = (Reserva.query
                .join(AsientoFuncion, Reserva.asiento_id == AsientoFuncion.id)
                .filter(AsientoFuncion.funcion_id == funcion_id,
                        Reserva.usuario_id == usuario_id,
                        Reserva.estado == EstadoReserva.ACTIVA,
                        Reserva.vence_en >= ahora)
                .all())
    if not reservas:
        raise ErrorAPI(
            "SIN_RESERVAS",
            "No tienes reservas activas en esta función y no indicaste "
            "asientos.",
            422,
        )
    return [r.asiento_id for r in reservas]


# --- Emisión de entradas con código único ---------------------------------

def _crear_entrada_con_codigo(compra_id, funcion_id, asiento_id):
    """Crea una entrada reintentando si el código único colisiona.

    La restricción UNIQUE en `entradas.codigo` es la defensa definitiva; aquí
    reintentamos con un savepoint para no romper la transacción principal.
    """
    for _ in range(MAX_REINTENTOS_CODIGO):
        codigo = generar_codigo_entrada()
        try:
            with db.session.begin_nested():  # savepoint
                entrada = Entrada(
                    codigo=codigo,
                    compra_id=compra_id,
                    funcion_id=funcion_id,
                    asiento_id=asiento_id,
                    estado=EstadoEntrada.ACTIVA,
                )
                db.session.add(entrada)
            return entrada
        except IntegrityError:
            # Colisión del código: el savepoint revierte y reintentamos.
            continue
    raise ErrorAPI(
        "CODIGO_NO_GENERADO",
        "No se pudo generar un código de entrada único. Intenta de nuevo.",
        500,
    )


# --- Compra ---------------------------------------------------------------

def comprar(datos: dict, usuario_id: int) -> tuple[dict, int]:
    """Procesa una compra con pago simulado. Devuelve (cuerpo, http_status).

    Pasos en una sola transacción con bloqueo de asientos:
      1. Validar función, cliente, método de pago y estado de cada asiento.
      2. Pago rechazado -> guardar compra rechazada, sin entradas, 402.
      3. Pago aprobado  -> vender asientos, convertir reservas, emitir entradas.
    """
    usuario = db.session.get(Usuario, usuario_id)

    funcion_id = datos.get("funcion_id")
    if not isinstance(funcion_id, int) or isinstance(funcion_id, bool):
        raise ErrorAPI("FUNCION_REQUERIDA",
                       "funcion_id es obligatorio y debe ser entero.", 422)

    metodo_pago = _validar_metodo_pago(usuario, datos.get("metodo_pago"))
    resultado = (datos.get("resultado_simulado") or "aprobado").strip().lower()
    if resultado not in ("aprobado", "rechazado"):
        raise ErrorAPI(
            "RESULTADO_INVALIDO",
            "resultado_simulado debe ser 'aprobado' o 'rechazado'.", 422)

    # La función debe existir y ser válida para vender (RN-08).
    funcion = obtener_funcion(funcion_id)
    _validar_funcion_reservable(funcion)

    # Asientos objetivo (del body o de mis reservas vigentes).
    ids_asientos = _resolver_asientos_objetivo(funcion_id, datos, usuario_id)

    try:
        # Bloqueo de filas de asientos, ordenadas por id.
        asientos = (AsientoFuncion.query
                    .filter(AsientoFuncion.id.in_(ids_asientos))
                    .order_by(AsientoFuncion.id)
                    .with_for_update()
                    .all())

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

        # Cliente de la compra (RN-05).
        cliente = _resolver_cliente(usuario, datos)
        ahora = ahora_utc()

        # Validar/ajustar el estado de cada asiento (RN-04).
        no_disponibles = []
        reservas_vencidas = []
        reservas_a_convertir = []

        for asiento in asientos:
            if asiento.estado == EstadoAsiento.VENDIDO:
                no_disponibles.append(asiento.id)
                continue

            if asiento.estado == EstadoAsiento.DISPONIBLE:
                # Se reserva primero dentro de la misma transacción.
                continue

            if asiento.estado == EstadoAsiento.RESERVADO:
                # Debe ser una reserva del mismo usuario y vigente.
                reserva = (Reserva.query
                           .filter_by(asiento_id=asiento.id,
                                      estado=EstadoReserva.ACTIVA)
                           .order_by(Reserva.id.desc())
                           .first())
                if reserva is None:
                    # Reservado sin reserva activa: estado inconsistente -> no disp.
                    no_disponibles.append(asiento.id)
                elif reserva.usuario_id != usuario_id:
                    no_disponibles.append(asiento.id)
                elif reserva.vence_en < ahora:
                    reservas_vencidas.append(asiento.id)
                else:
                    reservas_a_convertir.append(reserva)

        if reservas_vencidas:
            db.session.rollback()
            raise ErrorAPI(
                "RESERVA_VENCIDA",
                "Una o más reservas ya vencieron; vuelve a reservar.",
                409,
                detalle={"asientos": sorted(reservas_vencidas)},
            )
        if no_disponibles:
            db.session.rollback()
            raise ErrorAPI(
                "ASIENTO_NO_DISPONIBLE",
                "Uno o más asientos ya no están disponibles.",
                409,
                detalle={"asientos_no_disponibles": sorted(no_disponibles)},
            )

        total = funcion.precio * len(asientos)

        # ----- Pago RECHAZADO (RN-13) -----
        if resultado == "rechazado":
            return _procesar_rechazo(
                cliente, usuario, funcion, asientos, metodo_pago, total,
                reservas_a_convertir, usuario_id)

        # ----- Pago APROBADO -----
        return _procesar_aprobacion(
            cliente, usuario, funcion, asientos, metodo_pago, total,
            reservas_a_convertir, usuario_id, ahora)

    except ErrorAPI:
        raise
    except Exception:
        db.session.rollback()
        raise


def _procesar_rechazo(cliente, usuario, funcion, asientos, metodo_pago, total,
                      reservas_a_convertir, usuario_id):
    """Guarda una compra rechazada sin emitir entradas (RN-13).

    Los asientos que ya estaban reservados por el usuario siguen reservados con
    su vence_en. Los asientos que estaban disponibles NO se reservan (no hubo
    pago), por lo que se deja todo como estaba. Devuelve 402.
    """
    compra = Compra(
        cliente_id=cliente.id,
        usuario_id=usuario_id,
        funcion_id=funcion.id,
        total=total,
        metodo_pago=metodo_pago,
        estado_pago=EstadoPago.RECHAZADO,
        creado_en=ahora_utc(),
    )
    db.session.add(compra)
    db.session.flush()

    registrar_auditoria(
        usuario_id=usuario_id, accion="compra_rechazada", entidad="compras",
        entidad_id=compra.id,
        detalle={"funcion_id": funcion.id,
                 "asientos": [a.id for a in asientos], "total": total})
    # Commit de la compra rechazada ANTES de responder.
    db.session.commit()

    # vence_en: el más próximo de las reservas vigentes del usuario (si las hay).
    vence_en = None
    if reservas_a_convertir:
        vence_en = min(r.vence_en for r in reservas_a_convertir)
    from app.utils.tiempo import a_iso_bogota
    cuerpo = {
        "error": {
            "codigo": "PAGO_RECHAZADO",
            "mensaje": "El pago fue rechazado. No se generaron entradas.",
            "detalle": {
                "compra_id": compra.id,
                "vence_en": a_iso_bogota(vence_en),
            },
        }
    }
    return cuerpo, 402


def _procesar_aprobacion(cliente, usuario, funcion, asientos, metodo_pago,
                         total, reservas_a_convertir, usuario_id, ahora):
    """Vende los asientos, convierte reservas y emite entradas. Devuelve 201."""
    compra = Compra(
        cliente_id=cliente.id,
        usuario_id=usuario_id,
        funcion_id=funcion.id,
        total=total,
        metodo_pago=metodo_pago,
        estado_pago=EstadoPago.APROBADO,
        creado_en=ahora,
    )
    db.session.add(compra)
    db.session.flush()

    # Convertir las reservas vigentes del usuario.
    for reserva in reservas_a_convertir:
        reserva.estado = EstadoReserva.CONVERTIDA

    # Vender asientos y emitir una entrada por asiento.
    entradas_detalle = []
    for asiento in asientos:
        asiento.estado = EstadoAsiento.VENDIDO
        entrada = _crear_entrada_con_codigo(compra.id, funcion.id, asiento.id)
        db.session.flush()
        entradas_detalle.append({
            "id": entrada.id,
            "codigo": entrada.codigo,
            "fila": asiento.fila,
            "numero": asiento.numero,
            "estado": entrada.estado.value,
        })

    registrar_auditoria(
        usuario_id=usuario_id, accion="compra_aprobada", entidad="compras",
        entidad_id=compra.id,
        detalle={"funcion_id": funcion.id, "total": total,
                 "asientos": [a.id for a in asientos],
                 "entradas": [e["codigo"] for e in entradas_detalle]})
    db.session.commit()

    from app.utils.serializadores import serializar_compra
    cuerpo = {
        "compra": serializar_compra(compra),
        "entradas": entradas_detalle,
    }
    return cuerpo, 201


# --- Consultas ------------------------------------------------------------

def listar_mis_compras(usuario_id: int) -> list[dict]:
    """Lista SOLO las compras aprobadas del cliente autenticado (RN-12).

    Incluye función, película y las entradas (código, asiento, estado).
    """
    from app.utils.serializadores import serializar_compra, serializar_entrada

    cliente = Cliente.query.filter_by(usuario_id=usuario_id).first()
    if cliente is None:
        return []

    compras = (Compra.query
               .filter_by(cliente_id=cliente.id,
                          estado_pago=EstadoPago.APROBADO)
               .order_by(Compra.creado_en.desc())
               .all())

    resultado = []
    for compra in compras:
        datos = serializar_compra(compra)
        datos["entradas"] = [
            serializar_entrada(e) for e in
            Entrada.query.filter_by(compra_id=compra.id)
            .order_by(Entrada.id).all()
        ]
        resultado.append(datos)
    return resultado


def listar_ventas(usuario_id: int, desde=None, hasta=None) -> list[dict]:
    """Historial de ventas aprobadas.

    - Taquillero: solo las compras que él registró.
    - Administrador: todas.
    Filtros opcionales por rango de fechas (desde/hasta en YYYY-MM-DD, Bogotá).
    Incluye cliente, función, asientos, total y método de pago.
    """
    from app.utils.serializadores import serializar_compra, serializar_entrada
    from app.utils.tiempo import parsear_dia_bogota

    usuario = db.session.get(Usuario, usuario_id)
    consulta = Compra.query.filter_by(estado_pago=EstadoPago.APROBADO)

    # Taquillero: solo lo suyo. Administrador: todo.
    if usuario.rol == RolUsuario.TAQUILLERO:
        consulta = consulta.filter(Compra.usuario_id == usuario_id)

    if desde:
        inicio_utc, _ = parsear_dia_bogota(desde)
        consulta = consulta.filter(Compra.creado_en >= inicio_utc)
    if hasta:
        _, fin_utc = parsear_dia_bogota(hasta)
        consulta = consulta.filter(Compra.creado_en <= fin_utc)

    compras = consulta.order_by(Compra.creado_en.desc()).all()

    resultado = []
    for compra in compras:
        datos = serializar_compra(compra)
        cliente = db.session.get(Cliente, compra.cliente_id)
        datos["cliente"] = {
            "id": cliente.id if cliente else None,
            "nombre": cliente.nombre if cliente else None,
            "documento": cliente.documento if cliente else None,
            "contacto": cliente.contacto if cliente else None,
        }
        datos["entradas"] = [
            serializar_entrada(e) for e in
            Entrada.query.filter_by(compra_id=compra.id)
            .order_by(Entrada.id).all()
        ]
        resultado.append(datos)
    return resultado
