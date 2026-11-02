"""Utilidades de tiempo.

Todas las fechas se guardan en UTC (timestamptz). La conversión a la zona de
negocio (America/Bogota) se hace al presentar los datos, no al guardarlos.
"""

from datetime import datetime, timezone


def ahora_utc() -> datetime:
    """Devuelve la fecha y hora actual en UTC con zona horaria explícita.

    Se usa como valor por defecto en las columnas de fecha para que nunca se
    guarde una fecha "naive" (sin zona).
    """
    return datetime.now(timezone.utc)
