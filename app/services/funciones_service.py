"""Servicio de funciones: consulta pública y gestión de administrador.

Incluye la creación transaccional de una función con todos sus asientos, la
comprobación de solapamiento en la sala y el cálculo eficiente de asientos
disponibles (sin N+1).
"""

import string
from datetime import timedelta

from sqlalchemy import func

from app.extensions import db
from app.models.pelicula import Pelicula
from app.models.sala import Sala
from app.models.funcion import Funcion
from app.models.asiento_funcion import AsientoFuncion
from app.models.reserva import Reserva
from app.models.compra import Compra
from app.models.entrada import Entrada
from app.models.enums import EstadoFuncion, EstadoAsiento
from app.services.auditoria_service import registrar_auditoria
from app.services.peliculas_service import obtener_pelicula
from app.services.salas_service import obtener_sala
from app.utils.errores import ErrorAPI
from app.utils.funciones_tiempo import funcion_ya_inicio
from app.utils.tiempo import ahora_utc, parsear_iso_a_utc, parsear_dia_bogota

# Margen de limpieza entre funciones de una misma sala (minutos).
MARGEN_MINUTOS = 15


# --- Consulta de asientos disponibles (agregada, sin N+1) -----------------

def _mapa_asientos_disponibles(funcion_ids: list[int]) -> dict[int, int]:
    """Cuenta asientos DISPONIBLES por función en UNA sola consulta.

    Devuelve {funcion_id: cantidad}. Las funciones sin disponibles no
    aparecen; quien consulta debe asumir 0 en ese caso.
    """
    if not funcion_ids:
        return {}
    filas = (db.session.query(
                AsientoFuncion.funcion_id,
                func.count(AsientoFuncion.id))
             .filter(AsientoFuncion.funcion_id.in_(funcion_ids),
                     AsientoFuncion.estado == EstadoAsiento.DISPONIBLE)
             .group_by(AsientoFuncion.funcion_id)
             .all())
    return {fid: cantidad for fid, cantidad in filas}


def asientos_disponibles_de(funcion_id: int) -> int:
    """Cuenta los asientos disponibles de una sola función."""
    return _mapa_asientos_disponibles([funcion_id]).get(funcion_id, 0)


# --- Consultas ------------------------------------------------------------

def listar_funciones(pelicula_id=None, fecha=None, todas=False):
    """Lista funciones y devuelve (funciones, mapa_disponibles).

    - Público (todas=False): solo estado activa, futuras (no iniciadas) y de
      películas activas.
    - Administrador (todas=True): incluye pasadas y canceladas.
    Filtros opcionales: pelicula_id y fecha (YYYY-MM-DD en hora de Bogotá).
    Ordenadas por inicio.
    """
    consulta = Funcion.query.join(Pelicula, Funcion.pelicula_id == Pelicula.id)

    if not todas:
        # Vista pública: activas, futuras y de películas activas.
        consulta = consulta.filter(
            Funcion.estado == EstadoFuncion.ACTIVA,
            Funcion.inicio > ahora_utc(),
            Pelicula.activa.is_(True),
        )

    if pelicula_id is not None:
        consulta = consulta.filter(Funcion.pelicula_id == pelicula_id)

    if fecha:
        inicio_utc, fin_utc = parsear_dia_bogota(fecha)
        consulta = consulta.filter(
            Funcion.inicio >= inicio_utc, Funcion.inicio <= fin_utc)

    funciones = consulta.order_by(Funcion.inicio).all()
    mapa = _mapa_asientos_disponibles([f.id for f in funciones])
    return funciones, mapa


def obtener_funcion(funcion_id: int) -> Funcion:
    """Obtiene una función por id o lanza 404.

    Es para el detalle público: incluye funciones ya iniciadas (para mostrar
    su estado), por eso no filtra por estado ni por fecha.
    """
    funcion = db.session.get(Funcion, funcion_id)
    if funcion is None:
        raise ErrorAPI("FUNCION_NO_ENCONTRADA", "La función no existe.", 404)
    return funcion


# --- Solapamiento ---------------------------------------------------------

def _validar_no_solapamiento(sala_id, inicio_utc, duracion_min,
                             excluir_funcion_id=None):
    """Verifica que la nueva función no se solape con otra activa en la sala.

    Dos funciones se solapan si sus intervalos [inicio, fin+margen) se cruzan.
    Lanza ErrorAPI(409, FUNCION_SOLAPADA) indicando la función en conflicto.
    """
    fin_nueva = inicio_utc + timedelta(minutes=(duracion_min or 0) + MARGEN_MINUTOS)

    # Candidatas: funciones activas de la misma sala (excepto ella misma).
    candidatas = (Funcion.query
                  .filter(Funcion.sala_id == sala_id,
                          Funcion.estado == EstadoFuncion.ACTIVA))
    if excluir_funcion_id is not None:
        candidatas = candidatas.filter(Funcion.id != excluir_funcion_id)

    for otra in candidatas.all():
        dur_otra = otra.pelicula.duracion_min if otra.pelicula else 0
        fin_otra = otra.inicio + timedelta(minutes=(dur_otra or 0) + MARGEN_MINUTOS)
        # Solapan si una empieza antes de que termine la otra (y viceversa).
        if inicio_utc < fin_otra and otra.inicio < fin_nueva:
            raise ErrorAPI(
                "FUNCION_SOLAPADA",
                f"La función se solapa con la función id {otra.id} "
                f"en la misma sala.",
                409,
                detalle={"funcion_en_conflicto": otra.id},
            )


# --- Generación de asientos ----------------------------------------------

def _generar_asientos(funcion: Funcion, sala: Sala) -> None:
    """Crea todos los asientos de la función en estado disponible (CA-01).

    Filas con letras A, B, C... según sala.filas; números 1..asientos_por_fila.
    """
    for i in range(sala.filas):
        letra = string.ascii_uppercase[i]
        for numero in range(1, sala.asientos_por_fila + 1):
            db.session.add(AsientoFuncion(
                funcion_id=funcion.id,
                fila=letra,
                numero=numero,
                estado=EstadoAsiento.DISPONIBLE,
            ))


# --- Alta / edición / baja ------------------------------------------------

def crear_funcion(datos: dict, admin_id: int) -> Funcion:
    """Crea una función y genera sus asientos en UNA sola transacción.

    Validaciones: película existe y activa, sala existe, inicio futuro,
    precio entero > 0 y sin solapamiento. Si algo falla, rollback total.
    """
    # La película debe existir y estar activa (no se crean funciones de
    # películas desactivadas).
    pelicula = obtener_pelicula(datos.get("pelicula_id"), solo_activa=False) \
        if datos.get("pelicula_id") is not None else None
    if pelicula is None:
        raise ErrorAPI("CAMPOS_REQUERIDOS", "pelicula_id es obligatorio.", 422)
    if not pelicula.activa:
        raise ErrorAPI("PELICULA_INACTIVA",
                       "No se pueden crear funciones de una película "
                       "desactivada.", 409)

    if datos.get("sala_id") is None:
        raise ErrorAPI("CAMPOS_REQUERIDOS", "sala_id es obligatorio.", 422)
    sala = obtener_sala(datos["sala_id"])

    inicio_utc = parsear_iso_a_utc(datos.get("inicio"))
    if inicio_utc <= ahora_utc():
        raise ErrorAPI("INICIO_NO_FUTURO",
                       "La hora de inicio debe ser futura.", 422)

    precio = datos.get("precio")
    if isinstance(precio, bool) or not isinstance(precio, int) or precio <= 0:
        raise ErrorAPI("PRECIO_INVALIDO",
                       "El precio debe ser un entero mayor que 0.", 422)

    # Sin solapamiento con otras funciones activas de la misma sala.
    _validar_no_solapamiento(sala.id, inicio_utc, pelicula.duracion_min)

    try:
        funcion = Funcion(
            pelicula_id=pelicula.id,
            sala_id=sala.id,
            inicio=inicio_utc,
            precio=precio,
            estado=EstadoFuncion.ACTIVA,
        )
        db.session.add(funcion)
        db.session.flush()  # para obtener el id

        _generar_asientos(funcion, sala)

        registrar_auditoria(
            usuario_id=admin_id, accion="crear_funcion", entidad="funciones",
            entidad_id=funcion.id,
            detalle={"pelicula_id": pelicula.id, "sala_id": sala.id,
                     "inicio_utc": inicio_utc.isoformat()})
        db.session.commit()
    except Exception:
        # Rollback total: nunca dejar la función sin sus asientos.
        db.session.rollback()
        raise
    return funcion


def _tiene_ventas(funcion_id: int) -> bool:
    """True si la función tiene asientos reservados o vendidos."""
    return db.session.query(
        AsientoFuncion.query.filter(
            AsientoFuncion.funcion_id == funcion_id,
            AsientoFuncion.estado.in_(
                [EstadoAsiento.RESERVADO, EstadoAsiento.VENDIDO])
        ).exists()
    ).scalar()


def editar_funcion(funcion_id: int, datos: dict, admin_id: int) -> Funcion:
    """Edita una función.

    - No se puede editar una función cancelada o ya iniciada.
    - Si tiene asientos reservados o vendidos, SOLO se puede cambiar el precio
      (cambiar sala, inicio o película -> 409 FUNCION_CON_VENTAS).
    """
    funcion = obtener_funcion(funcion_id)

    if funcion.estado == EstadoFuncion.CANCELADA:
        raise ErrorAPI("FUNCION_CANCELADA",
                       "No se puede editar una función cancelada.", 409)
    if funcion_ya_inicio(funcion):
        raise ErrorAPI("FUNCION_YA_INICIADA",
                       "No se puede editar una función ya iniciada.", 409)

    quiere_cambiar_estructura = any(
        datos.get(c) is not None for c in ("sala_id", "inicio", "pelicula_id"))
    tiene_ventas = _tiene_ventas(funcion.id)

    if tiene_ventas and quiere_cambiar_estructura:
        raise ErrorAPI(
            "FUNCION_CON_VENTAS",
            "La función tiene reservas o ventas; solo se puede cambiar el "
            "precio.",
            409,
        )

    cambios = {}

    # Cambio de precio (siempre permitido mientras no esté cancelada/iniciada).
    if datos.get("precio") is not None:
        precio = datos["precio"]
        if isinstance(precio, bool) or not isinstance(precio, int) or precio <= 0:
            raise ErrorAPI("PRECIO_INVALIDO",
                           "El precio debe ser un entero mayor que 0.", 422)
        funcion.precio = precio
        cambios["precio"] = precio

    # Cambios de estructura solo si NO hay ventas (ya validado arriba).
    if not tiene_ventas and quiere_cambiar_estructura:
        funcion = _editar_estructura(funcion, datos, cambios)

    registrar_auditoria(
        usuario_id=admin_id, accion="editar_funcion", entidad="funciones",
        entidad_id=funcion.id, detalle={"cambios": cambios})
    db.session.commit()
    return funcion


def _editar_estructura(funcion: Funcion, datos: dict, cambios: dict) -> Funcion:
    """Aplica cambios de película, sala o inicio a una función sin ventas.

    Si cambia la sala, regenera los asientos según la nueva distribución.
    """
    nueva_pelicula = funcion.pelicula
    if datos.get("pelicula_id") is not None:
        nueva_pelicula = obtener_pelicula(datos["pelicula_id"])
        if not nueva_pelicula.activa:
            raise ErrorAPI("PELICULA_INACTIVA",
                           "La película está desactivada.", 409)
        funcion.pelicula_id = nueva_pelicula.id
        cambios["pelicula_id"] = nueva_pelicula.id

    nueva_sala = funcion.sala
    cambia_sala = datos.get("sala_id") is not None
    if cambia_sala:
        nueva_sala = obtener_sala(datos["sala_id"])
        cambios["sala_id"] = nueva_sala.id

    nuevo_inicio = funcion.inicio
    if datos.get("inicio") is not None:
        nuevo_inicio = parsear_iso_a_utc(datos["inicio"])
        if nuevo_inicio <= ahora_utc():
            raise ErrorAPI("INICIO_NO_FUTURO",
                           "La hora de inicio debe ser futura.", 422)
        funcion.inicio = nuevo_inicio
        cambios["inicio_utc"] = nuevo_inicio.isoformat()

    # Revalidar solapamiento con la nueva configuración.
    _validar_no_solapamiento(
        nueva_sala.id, nuevo_inicio, nueva_pelicula.duracion_min,
        excluir_funcion_id=funcion.id)

    # Si cambió la sala, regeneramos los asientos (no hay ventas que perder).
    if cambia_sala and nueva_sala.id != funcion.sala_id:
        AsientoFuncion.query.filter_by(funcion_id=funcion.id).delete()
        funcion.sala_id = nueva_sala.id
        db.session.flush()
        _generar_asientos(funcion, nueva_sala)

    return funcion


def eliminar_funcion(funcion_id: int, admin_id: int) -> None:
    """Elimina una función y sus asientos SOLO si no tiene ventas.

    Si tiene compras, entradas o reservas, 409 sugiriendo cancelar (Fase B5).
    """
    funcion = obtener_funcion(funcion_id)

    tiene_compras = db.session.query(
        Compra.query.filter_by(funcion_id=funcion.id).exists()).scalar()
    tiene_entradas = db.session.query(
        Entrada.query.filter_by(funcion_id=funcion.id).exists()).scalar()
    tiene_reservas = db.session.query(
        Reserva.query.join(AsientoFuncion,
                           Reserva.asiento_id == AsientoFuncion.id)
        .filter(AsientoFuncion.funcion_id == funcion.id).exists()).scalar()

    if tiene_compras or tiene_entradas or tiene_reservas:
        raise ErrorAPI(
            "FUNCION_CON_VENTAS",
            "La función tiene ventas; use la opción de cancelar.", 409)

    # Sin ventas: borramos asientos y función.
    AsientoFuncion.query.filter_by(funcion_id=funcion.id).delete()
    registrar_auditoria(
        usuario_id=admin_id, accion="eliminar_funcion", entidad="funciones",
        entidad_id=funcion.id,
        detalle={"pelicula_id": funcion.pelicula_id, "sala_id": funcion.sala_id})
    db.session.delete(funcion)
    db.session.commit()
