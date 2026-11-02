"""Utilidades de tiempo.

Todas las fechas se guardan en UTC (timestamptz). La conversión a la zona de
negocio (America/Bogota) se hace al presentar los datos, no al guardarlos.
"""

import os
from datetime import datetime, timezone, date, time
from zoneinfo import ZoneInfo

from app.utils.errores import ErrorAPI

# Zona horaria de negocio. Configurable por .env; por defecto America/Bogota.
ZONA_BOGOTA = ZoneInfo(os.getenv("ZONA_HORARIA", "America/Bogota"))


def ahora_utc() -> datetime:
    """Devuelve la fecha y hora actual en UTC con zona horaria explícita.

    Se usa como valor por defecto en las columnas de fecha para que nunca se
    guarde una fecha "naive" (sin zona).
    """
    return datetime.now(timezone.utc)


def a_utc(fecha: datetime) -> datetime:
    """Convierte un datetime a UTC.

    Si el datetime viene SIN zona (naive), se interpreta en la zona de negocio
    (America/Bogota) antes de pasarlo a UTC. Si ya tiene zona, se respeta.
    """
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=ZONA_BOGOTA)
    return fecha.astimezone(timezone.utc)


def parsear_iso_a_utc(texto: str) -> datetime:
    """Parsea una fecha ISO 8601 y la devuelve en UTC.

    Si no trae zona horaria, se asume America/Bogota. Lanza ErrorAPI(422) si
    el formato no es válido.
    """
    if not texto or not isinstance(texto, str):
        raise ErrorAPI("FECHA_INVALIDA",
                       "La fecha de inicio es obligatoria.", 422)
    try:
        # fromisoformat acepta "2026-11-05T20:00:00" y "...+00:00"/"...-05:00".
        fecha = datetime.fromisoformat(texto.strip())
    except ValueError:
        raise ErrorAPI(
            "FECHA_INVALIDA",
            "El formato de la fecha no es válido. Usa ISO 8601, "
            "por ejemplo 2026-11-05T20:00:00.",
            422,
        )
    return a_utc(fecha)


def parsear_dia_bogota(texto: str) -> tuple[datetime, datetime]:
    """Dado 'YYYY-MM-DD' (día en Bogotá), devuelve el rango [inicio, fin) en UTC.

    Sirve para filtrar funciones de un día concreto en hora local, guardadas
    en UTC. Lanza ErrorAPI(422) si el formato es inválido.
    """
    try:
        dia = date.fromisoformat(texto.strip())
    except (ValueError, AttributeError):
        raise ErrorAPI(
            "FECHA_INVALIDA",
            "El formato de la fecha debe ser YYYY-MM-DD.", 422)

    inicio_local = datetime.combine(dia, time.min, tzinfo=ZONA_BOGOTA)
    fin_local = datetime.combine(dia, time.max, tzinfo=ZONA_BOGOTA)
    return inicio_local.astimezone(timezone.utc), fin_local.astimezone(timezone.utc)


def a_iso_bogota(fecha: datetime | None) -> str | None:
    """Devuelve la fecha en ISO 8601 con la zona de negocio (America/Bogota).

    Las fechas se guardan en UTC; aquí se presentan en hora local con offset.
    """
    if fecha is None:
        return None
    # Si por alguna razón viene naive, asumimos que está en UTC.
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone(ZONA_BOGOTA).isoformat()
