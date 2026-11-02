"""Blueprint de salas: consulta (admin y taquillero) y CRUD de administrador."""

from flask import Blueprint, jsonify, request

from app.services.salas_service import (
    listar_salas, obtener_sala, crear_sala, editar_sala, eliminar_sala,
)
from app.utils.autorizacion import rol_requerido, id_usuario_actual
from app.utils.serializadores import serializar_sala

bp_salas = Blueprint("salas", __name__)


@bp_salas.get("/salas")
@rol_requerido("administrador", "taquillero")
def listar():
    """Lista todas las salas (administrador y taquillero)."""
    salas = listar_salas()
    return jsonify({"salas": [serializar_sala(s) for s in salas]}), 200


@bp_salas.get("/salas/<int:sala_id>")
@rol_requerido("administrador", "taquillero")
def detalle(sala_id):
    """Detalle de una sala (administrador y taquillero)."""
    sala = obtener_sala(sala_id)
    return jsonify({"sala": serializar_sala(sala)}), 200


@bp_salas.post("/salas")
@rol_requerido("administrador")
def crear():
    """Administrador: crea una sala y calcula su capacidad."""
    datos = request.get_json(silent=True) or {}
    sala = crear_sala(datos, admin_id=id_usuario_actual())
    return jsonify({"sala": serializar_sala(sala)}), 201


@bp_salas.put("/salas/<int:sala_id>")
@rol_requerido("administrador")
def editar(sala_id):
    """Administrador: edita una sala."""
    datos = request.get_json(silent=True) or {}
    sala = editar_sala(sala_id, datos, admin_id=id_usuario_actual())
    return jsonify({"sala": serializar_sala(sala)}), 200


@bp_salas.delete("/salas/<int:sala_id>")
@rol_requerido("administrador")
def eliminar(sala_id):
    """Administrador: elimina una sala si no tiene funciones."""
    eliminar_sala(sala_id, admin_id=id_usuario_actual())
    return jsonify({"mensaje": "Sala eliminada."}), 200
