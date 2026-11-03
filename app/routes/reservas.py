"""Blueprint de reservas: crear, cancelar y consultar reservas propias."""

from flask import Blueprint, jsonify, request

from app.services.reservas_service import (
    reservar, cancelar_reserva, cancelar_mis_reservas_en_funcion,
    listar_mis_reservas,
)
from app.utils.autorizacion import rol_requerido, id_usuario_actual
from app.utils.errores import ErrorAPI
from app.utils.tiempo import a_iso_bogota

bp_reservas = Blueprint("reservas", __name__)


@bp_reservas.post("/reservas")
@rol_requerido("cliente", "taquillero")
def crear():
    """Reserva uno o varios asientos de una función (cliente o taquillero)."""
    datos = request.get_json(silent=True) or {}
    resultado = reservar(datos, usuario_id=id_usuario_actual())
    return jsonify({
        "reservas": resultado["reservas"],
        "vence_en": a_iso_bogota(resultado["vence_en"]),
        "segundos_restantes": resultado["segundos_restantes"],
    }), 201


@bp_reservas.get("/reservas/mias")
@rol_requerido("cliente", "taquillero")
def mias():
    """Lista mis reservas activas en una función (?funcion_id=)."""
    funcion_id = request.args.get("funcion_id", type=int)
    if funcion_id is None:
        raise ErrorAPI("FUNCION_REQUERIDA",
                       "Debes indicar funcion_id.", 422)
    reservas = listar_mis_reservas(funcion_id, id_usuario_actual())
    return jsonify({"reservas": reservas}), 200


@bp_reservas.post("/reservas/cancelar")
@rol_requerido("cliente", "taquillero")
def cancelar_todas_en_funcion():
    """Cancela todas mis reservas activas en una función (botón 'Volver')."""
    datos = request.get_json(silent=True) or {}
    funcion_id = datos.get("funcion_id")
    if not isinstance(funcion_id, int) or isinstance(funcion_id, bool):
        raise ErrorAPI("FUNCION_REQUERIDA",
                       "funcion_id es obligatorio y debe ser entero.", 422)
    canceladas = cancelar_mis_reservas_en_funcion(
        funcion_id, id_usuario_actual())
    return jsonify({"canceladas": canceladas}), 200


@bp_reservas.delete("/reservas/<int:reserva_id>")
@rol_requerido("cliente", "taquillero")
def cancelar(reserva_id):
    """Cancela una reserva propia y activa."""
    cancelar_reserva(reserva_id, id_usuario_actual())
    return jsonify({"mensaje": "Reserva cancelada."}), 200
