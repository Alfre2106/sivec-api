"""Servicio de salas: consulta y gestión.

Las salas definen la distribución de asientos. No se permite alterar su
geometría si ya tienen funciones activas (desajustaría los mapas de asientos).
"""

from app.extensions import db
from app.models.sala import Sala
from app.models.funcion import Funcion
from app.models.enums import EstadoFuncion
from app.services.auditoria_service import registrar_auditoria
from app.utils.errores import ErrorAPI
from app.utils.validaciones import texto, validar_entero_en_rango


def listar_salas() -> list[Sala]:
    """Lista todas las salas ordenadas por nombre."""
    return Sala.query.order_by(Sala.nombre).all()


def obtener_sala(sala_id: int) -> Sala:
    """Obtiene una sala por id o lanza 404."""
    sala = db.session.get(Sala, sala_id)
    if sala is None:
        raise ErrorAPI("SALA_NO_ENCONTRADA", "La sala no existe.", 404)
    return sala


def _tiene_funciones_activas(sala_id: int) -> bool:
    """True si la sala tiene al menos una función en estado activa."""
    return db.session.query(
        Funcion.query.filter_by(
            sala_id=sala_id, estado=EstadoFuncion.ACTIVA).exists()
    ).scalar()


def _tiene_funciones(sala_id: int) -> bool:
    """True si la sala tiene cualquier función (de cualquier estado)."""
    return db.session.query(
        Funcion.query.filter_by(sala_id=sala_id).exists()
    ).scalar()


def crear_sala(datos: dict, admin_id: int) -> Sala:
    """Crea una sala y calcula su capacidad = filas * asientos_por_fila."""
    nombre = texto(datos.get("nombre"), "nombre", obligatorio=True, maximo=80)

    filas = validar_entero_en_rango(
        datos.get("filas"), "filas", 1, 26, codigo="FILAS_INVALIDAS")
    asientos_por_fila = validar_entero_en_rango(
        datos.get("asientos_por_fila"), "asientos_por_fila", 1, 30,
        codigo="ASIENTOS_INVALIDOS")

    sala = Sala(
        nombre=nombre,
        filas=filas,
        asientos_por_fila=asientos_por_fila,
        capacidad=filas * asientos_por_fila,
    )
    db.session.add(sala)
    db.session.flush()

    registrar_auditoria(
        usuario_id=admin_id, accion="crear_sala", entidad="salas",
        entidad_id=sala.id,
        detalle={"nombre": nombre, "capacidad": sala.capacidad})
    db.session.commit()
    return sala


def editar_sala(sala_id: int, datos: dict, admin_id: int) -> Sala:
    """Edita una sala.

    No permite cambiar `filas` ni `asientos_por_fila` si la sala ya tiene
    funciones activas (409 SALA_CON_FUNCIONES).
    """
    sala = obtener_sala(sala_id)
    cambios = {}

    # Si se intenta cambiar la geometría (filas o asientos_por_fila) y la sala
    # ya tiene funciones activas, se rechaza para no desajustar los mapas.
    intenta_cambiar_geometria = (datos.get("filas") is not None
                                 or datos.get("asientos_por_fila") is not None)
    if intenta_cambiar_geometria and _tiene_funciones_activas(sala.id):
        raise ErrorAPI(
            "SALA_CON_FUNCIONES",
            "No se puede cambiar la distribución de una sala con "
            "funciones activas.",
            409,
        )

    if datos.get("nombre") is not None:
        nombre = texto(datos["nombre"], "nombre", maximo=80)
        if nombre:
            sala.nombre = nombre
            cambios["nombre"] = nombre

    if datos.get("filas") is not None:
        sala.filas = validar_entero_en_rango(
            datos["filas"], "filas", 1, 26, codigo="FILAS_INVALIDAS")
        cambios["filas"] = sala.filas

    if datos.get("asientos_por_fila") is not None:
        sala.asientos_por_fila = validar_entero_en_rango(
            datos["asientos_por_fila"], "asientos_por_fila", 1, 30,
            codigo="ASIENTOS_INVALIDOS")
        cambios["asientos_por_fila"] = sala.asientos_por_fila

    # Recalcular capacidad si cambió la geometría.
    sala.capacidad = sala.filas * sala.asientos_por_fila
    cambios["capacidad"] = sala.capacidad

    registrar_auditoria(
        usuario_id=admin_id, accion="editar_sala", entidad="salas",
        entidad_id=sala.id, detalle={"cambios": cambios})
    db.session.commit()
    return sala


def eliminar_sala(sala_id: int, admin_id: int) -> None:
    """Elimina una sala solo si no tiene ninguna función; si no, 409."""
    sala = obtener_sala(sala_id)
    if _tiene_funciones(sala.id):
        raise ErrorAPI(
            "SALA_CON_FUNCIONES",
            "No se puede eliminar una sala que tiene funciones.", 409)

    registrar_auditoria(
        usuario_id=admin_id, accion="eliminar_sala", entidad="salas",
        entidad_id=sala.id, detalle={"nombre": sala.nombre})
    db.session.delete(sala)
    db.session.commit()
