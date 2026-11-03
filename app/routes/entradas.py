"""Blueprint de entradas: detalle y código QR (con control de permisos)."""

from flask import Blueprint, jsonify, Response

from app.services.entradas_service import (
    obtener_entrada, verificar_acceso_entrada, generar_qr_png,
)
from app.utils.autorizacion import rol_requerido, id_usuario_actual
from app.utils.serializadores import serializar_entrada

bp_entradas = Blueprint("entradas", __name__)


@bp_entradas.get("/entradas/<int:entrada_id>")
@rol_requerido("cliente", "taquillero", "administrador")
def detalle(entrada_id):
    """Detalle de una entrada (dueño, taquillero o administrador)."""
    entrada = obtener_entrada(entrada_id)
    verificar_acceso_entrada(entrada, id_usuario_actual())
    datos = serializar_entrada(entrada)
    datos["funcion_id"] = entrada.funcion_id
    datos["compra_id"] = entrada.compra_id
    return jsonify({"entrada": datos}), 200


@bp_entradas.get("/entradas/<int:entrada_id>/qr")
@rol_requerido("cliente", "taquillero", "administrador")
def qr(entrada_id):
    """Devuelve la imagen PNG del código QR de la entrada."""
    entrada = obtener_entrada(entrada_id)
    verificar_acceso_entrada(entrada, id_usuario_actual())
    png = generar_qr_png(entrada.codigo)
    return Response(png, mimetype="image/png")
