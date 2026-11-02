"""Blueprint de salud (healthcheck).

Expone GET /api/salud para comprobar que la API está viva y que la conexión
a la base de datos responde. Útil para monitoreo y para verificar el despliegue.
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify
from sqlalchemy import text

from app.extensions import db

# Nota: el prefijo /api se aplica al registrar el blueprint en create_app.
bp_salud = Blueprint("salud", __name__)


@bp_salud.get("/salud")
def salud():
    """Devuelve el estado de la API y de la base de datos."""
    # Comprobamos la conexión a la BD con una consulta trivial.
    try:
        db.session.execute(text("SELECT 1"))
        estado_bd = "ok"
    except Exception:  # noqa: BLE001 - queremos capturar cualquier fallo de conexión
        estado_bd = "error"

    cuerpo = {
        "estado": "ok" if estado_bd == "ok" else "degradado",
        "servicio": "sivec-api",
        "base_datos": estado_bd,
        # Fecha en UTC con formato ISO 8601 y zona
        "hora_utc": datetime.now(timezone.utc).isoformat(),
    }
    # Si la BD falla, devolvemos 503 para que el monitoreo lo detecte.
    return jsonify(cuerpo), (200 if estado_bd == "ok" else 503)
