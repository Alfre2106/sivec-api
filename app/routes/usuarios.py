"""Blueprint de gestión de usuarios (solo administrador).

CRUD de /api/usuarios: listar (con filtro por rol), crear (taquillero o
administrador), editar y desactivar. Todas las acciones se auditan en el
servicio correspondiente.
"""

from flask import Blueprint, jsonify, request

from app.services.usuarios_service import (
    listar_usuarios, crear_usuario, editar_usuario, desactivar_usuario,
)
from app.utils.autorizacion import rol_requerido, id_usuario_actual
from app.utils.serializadores import serializar_usuario
from app.utils.validaciones import requerir_campos

bp_usuarios = Blueprint("usuarios", __name__)


@bp_usuarios.get("/usuarios")
@rol_requerido("administrador")
def listar():
    """Lista los usuarios. Filtro opcional por rol: ?rol=taquillero."""
    rol = request.args.get("rol")
    usuarios = listar_usuarios(rol)
    return jsonify({
        "usuarios": [serializar_usuario(u) for u in usuarios]
    }), 200


@bp_usuarios.post("/usuarios")
@rol_requerido("administrador")
def crear():
    """Crea un usuario taquillero o administrador."""
    datos = request.get_json(silent=True) or {}
    requerir_campos(datos, ["nombre", "correo", "password", "rol"])

    usuario = crear_usuario(datos, admin_id=id_usuario_actual())
    return jsonify({"usuario": serializar_usuario(usuario)}), 201


@bp_usuarios.put("/usuarios/<int:usuario_id>")
@rol_requerido("administrador")
def editar(usuario_id):
    """Edita un usuario existente."""
    datos = request.get_json(silent=True) or {}
    usuario = editar_usuario(usuario_id, datos, admin_id=id_usuario_actual())
    return jsonify({"usuario": serializar_usuario(usuario)}), 200


@bp_usuarios.delete("/usuarios/<int:usuario_id>")
@rol_requerido("administrador")
def desactivar(usuario_id):
    """Desactiva un usuario (no lo elimina de la base de datos)."""
    usuario = desactivar_usuario(usuario_id, admin_id=id_usuario_actual())
    return jsonify({"usuario": serializar_usuario(usuario)}), 200
