"""Blueprint de funciones: consulta pública y CRUD de administrador."""

from flask import Blueprint, jsonify, request

from app.services.funciones_service import (
    listar_funciones, obtener_funcion, asientos_disponibles_de,
    crear_funcion, editar_funcion, eliminar_funcion, mapa_asientos,
    cancelar_funcion, compras_afectadas_funcion,
)
from flask_jwt_extended import verify_jwt_in_request

from app.utils.autorizacion import (
    rol_requerido, id_usuario_actual, rol_usuario_actual,
)
from app.utils.serializadores import serializar_funcion

bp_funciones = Blueprint("funciones", __name__)


def _es_admin_autenticado() -> bool:
    """Indica si hay un administrador autenticado (para ?todas=1).

    No exige token: si no hay token válido, devuelve False en vez de fallar,
    porque el listado de funciones es público.
    """
    try:
        verify_jwt_in_request(optional=True)
        return rol_usuario_actual() == "administrador"
    except Exception:  # noqa: BLE001
        return False


@bp_funciones.get("/funciones")
def listar():
    """Público: funciones activas y futuras de películas activas.

    Filtros: ?pelicula_id= y ?fecha=YYYY-MM-DD (hora de Bogotá).
    Administrador con ?todas=1 ve también pasadas y canceladas.
    """
    pelicula_id = request.args.get("pelicula_id", type=int)
    fecha = request.args.get("fecha")
    pide_todas = request.args.get("todas") in ("1", "true", "True")

    # Solo un administrador autenticado puede pedir "todas".
    todas = pide_todas and _es_admin_autenticado()

    funciones, mapa = listar_funciones(
        pelicula_id=pelicula_id, fecha=fecha, todas=todas)
    return jsonify({
        "funciones": [
            serializar_funcion(f, mapa.get(f.id, 0)) for f in funciones
        ]
    }), 200


@bp_funciones.get("/funciones/<int:funcion_id>")
def detalle(funcion_id):
    """Público: detalle de una función (incluye iniciadas, con su estado)."""
    funcion = obtener_funcion(funcion_id)
    disponibles = asientos_disponibles_de(funcion.id)
    return jsonify({"funcion": serializar_funcion(funcion, disponibles)}), 200


@bp_funciones.get("/funciones/<int:funcion_id>/asientos")
def asientos(funcion_id):
    """Público (token opcional): mapa de asientos de la función.

    Si viene un token válido, marca 'mio' en los asientos reservados por ese
    usuario e incluye su 'vence_en'.
    """
    usuario_id = None
    try:
        verify_jwt_in_request(optional=True)
        usuario_id = id_usuario_actual()
    except Exception:  # noqa: BLE001 - sin token válido, se trata como anónimo
        usuario_id = None

    return jsonify(mapa_asientos(funcion_id, usuario_id)), 200


@bp_funciones.post("/funciones")
@rol_requerido("administrador")
def crear():
    """Administrador: crea una función y genera sus asientos."""
    datos = request.get_json(silent=True) or {}
    funcion = crear_funcion(datos, admin_id=id_usuario_actual())
    disponibles = asientos_disponibles_de(funcion.id)
    return jsonify({"funcion": serializar_funcion(funcion, disponibles)}), 201


@bp_funciones.put("/funciones/<int:funcion_id>")
@rol_requerido("administrador")
def editar(funcion_id):
    """Administrador: edita una función (reglas de ventas e inicio)."""
    datos = request.get_json(silent=True) or {}
    funcion = editar_funcion(funcion_id, datos, admin_id=id_usuario_actual())
    disponibles = asientos_disponibles_de(funcion.id)
    return jsonify({"funcion": serializar_funcion(funcion, disponibles)}), 200


@bp_funciones.delete("/funciones/<int:funcion_id>")
@rol_requerido("administrador")
def eliminar(funcion_id):
    """Administrador: elimina una función si no tiene ventas."""
    eliminar_funcion(funcion_id, admin_id=id_usuario_actual())
    return jsonify({"mensaje": "Función eliminada."}), 200


@bp_funciones.post("/funciones/<int:funcion_id>/cancelar")
@rol_requerido("administrador")
def cancelar(funcion_id):
    """Administrador: cancela la función y anula sus entradas activas."""
    datos = request.get_json(silent=True) or {}
    resultado = cancelar_funcion(
        funcion_id, motivo=datos.get("motivo"), admin_id=id_usuario_actual())
    return jsonify(resultado), 200


@bp_funciones.get("/funciones/<int:funcion_id>/afectados")
@rol_requerido("administrador")
def afectados(funcion_id):
    """Administrador: compras afectadas por la función (para reembolso)."""
    compras = compras_afectadas_funcion(funcion_id)
    return jsonify({"compras_afectadas": compras}), 200
