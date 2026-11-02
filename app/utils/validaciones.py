"""Utilidades de validación y normalización de datos de entrada.

Las reglas de validación se concentran aquí para reutilizarlas en las rutas y
mantener mensajes de error uniformes y en español.
"""

import re

from app.utils.errores import ErrorAPI

# Expresión razonable para validar el formato de un correo electrónico.
_PATRON_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Longitud mínima de contraseña exigida por el proyecto.
LONGITUD_MINIMA_PASSWORD = 6


def normalizar_correo(correo: str) -> str:
    """Normaliza un correo: quita espacios y lo pasa a minúsculas."""
    return (correo or "").strip().lower()


def validar_correo(correo: str) -> str:
    """Normaliza y valida el formato de un correo. Devuelve el correo limpio.

    Lanza ErrorAPI(422) si está vacío o tiene formato inválido.
    """
    correo_limpio = normalizar_correo(correo)
    if not correo_limpio:
        raise ErrorAPI("CORREO_REQUERIDO", "El correo es obligatorio.", 422)
    if not _PATRON_CORREO.match(correo_limpio):
        raise ErrorAPI("CORREO_INVALIDO",
                       "El formato del correo no es válido.", 422)
    return correo_limpio


def validar_password(password: str) -> str:
    """Valida la contraseña (mínimo de caracteres). Devuelve la contraseña.

    Lanza ErrorAPI(422) si falta o es demasiado corta.
    """
    if not password:
        raise ErrorAPI("PASSWORD_REQUERIDA", "La contraseña es obligatoria.", 422)
    if len(password) < LONGITUD_MINIMA_PASSWORD:
        raise ErrorAPI(
            "PASSWORD_CORTA",
            f"La contraseña debe tener al menos {LONGITUD_MINIMA_PASSWORD} "
            "caracteres.",
            422,
        )
    return password


def requerir_campos(datos: dict, campos: list[str]) -> None:
    """Verifica que los campos obligatorios estén presentes y no vacíos.

    Lanza ErrorAPI(422) indicando cuáles faltan.
    """
    if not isinstance(datos, dict):
        raise ErrorAPI("CUERPO_INVALIDO",
                       "El cuerpo de la petición debe ser un JSON válido.", 422)
    faltantes = [c for c in campos
                 if datos.get(c) is None or str(datos.get(c)).strip() == ""]
    if faltantes:
        raise ErrorAPI(
            "CAMPOS_REQUERIDOS",
            f"Faltan campos obligatorios: {', '.join(faltantes)}.",
            422,
        )
