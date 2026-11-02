"""Blueprint de autenticación: registro, login y datos del usuario actual.

Las rutas solo reciben la petición, delegan en auth_service y responden.
"""

from flask import Blueprint, jsonify, request

from app.services.auth_service import registrar_cliente, iniciar_sesion
from app.services.usuarios_service import obtener_usuario
from app.utils.autorizacion import rol_requerido, id_usuario_actual
from app.utils.serializadores import serializar_usuario
from app.utils.validaciones import requerir_campos

bp_auth = Blueprint("auth", __name__)


@bp_auth.post("/auth/registro")
def registro():
    """Registro público: crea un usuario cliente y su ficha de cliente."""
    datos = request.get_json(silent=True) or {}
    requerir_campos(datos, ["nombre", "correo", "password"])

    token, usuario = registrar_cliente(datos)
    return jsonify({
        "token": token,
        "usuario": serializar_usuario(usuario),
    }), 201


@bp_auth.post("/auth/login")
def login():
    """Inicio de sesión: valida credenciales y devuelve token + usuario."""
    datos = request.get_json(silent=True) or {}
    requerir_campos(datos, ["correo", "password"])

    token, usuario = iniciar_sesion(datos)
    return jsonify({
        "token": token,
        "usuario": serializar_usuario(usuario),
    }), 200


@bp_auth.get("/auth/yo")
@rol_requerido()  # cualquier usuario autenticado (sin restringir rol)
def yo():
    """Devuelve los datos del usuario autenticado a partir del token."""
    usuario = obtener_usuario(id_usuario_actual())
    return jsonify({"usuario": serializar_usuario(usuario)}), 200
