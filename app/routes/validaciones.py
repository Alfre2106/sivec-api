"""Blueprint de validaciones: validar entrada en puerta e historial."""

from flask import Blueprint, jsonify, request

from app.services.validaciones_service import (
    validar_entrada, listar_validaciones,
)
from app.utils.autorizacion import rol_requerido, id_usuario_actual
from app.utils.validaciones import obtener_cuerpo_json

bp_validaciones = Blueprint("validaciones", __name__)


@bp_validaciones.post("/validaciones")
@rol_requerido("taquillero", "administrador")
def validar():
    """Valida un código de entrada. Responde 200 en todos los resultados."""
    datos = obtener_cuerpo_json()
    resultado = validar_entrada(datos, taquillero_id=id_usuario_actual())
    return jsonify(resultado), 200


@bp_validaciones.get("/validaciones")
@rol_requerido("taquillero", "administrador")
def historial():
    """Historial de validaciones (taquillero: propias; admin: todas)."""
    registros = listar_validaciones(
        id_usuario_actual(),
        resultado=request.args.get("resultado"),
        desde=request.args.get("desde"),
        hasta=request.args.get("hasta"),
        limite=request.args.get("limite"),
    )
    return jsonify({"validaciones": registros}), 200
