"""Blueprint de compras y consultas asociadas (mis-compras, ventas)."""

from flask import Blueprint, jsonify, request

from app.services.compras_service import (
    comprar, listar_mis_compras, listar_ventas,
)
from app.utils.autorizacion import rol_requerido, id_usuario_actual

bp_compras = Blueprint("compras", __name__)


@bp_compras.post("/compras")
@rol_requerido("cliente", "taquillero")
def crear():
    """Confirma una compra y simula el pago (cliente o taquillero)."""
    datos = request.get_json(silent=True) or {}
    cuerpo, status = comprar(datos, usuario_id=id_usuario_actual())
    return jsonify(cuerpo), status


@bp_compras.get("/mis-compras")
@rol_requerido("cliente")
def mis_compras():
    """Cliente: sus compras aprobadas con función, película y entradas."""
    compras = listar_mis_compras(id_usuario_actual())
    return jsonify({"compras": compras}), 200


@bp_compras.get("/ventas")
@rol_requerido("taquillero", "administrador")
def ventas():
    """Historial de ventas: taquillero (propias) o administrador (todas)."""
    desde = request.args.get("desde")
    hasta = request.args.get("hasta")
    historial = listar_ventas(id_usuario_actual(), desde=desde, hasta=hasta)
    return jsonify({"ventas": historial}), 200
