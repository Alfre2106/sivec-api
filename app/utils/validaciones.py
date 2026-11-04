"""Utilidades de validación y normalización de datos de entrada.

Las reglas de validación se concentran aquí para reutilizarlas en las rutas y
mantener mensajes de error uniformes y en español.

Principio: NUNCA se asume el tipo de un dato recibido. Todo valor que llega en
un cuerpo JSON pasa por estos validadores (texto, entero, id, booleano), que
responden 422 con un mensaje claro en lugar de dejar que una operación de
Python o un límite de PostgreSQL termine en un error 500.
"""

import re

from flask import request

from app.utils.errores import ErrorAPI

# Expresión razonable para validar el formato de un correo electrónico.
_PATRON_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Longitud mínima de contraseña exigida por el proyecto.
LONGITUD_MINIMA_PASSWORD = 6
# bcrypt solo usa los primeros 72 bytes: más largo se rechaza para no truncar en silencio.
LONGITUD_MAXIMA_PASSWORD_BYTES = 72
# Mayor valor que cabe en una columna integer de PostgreSQL.
ID_MAXIMO = 2_147_483_647
# Longitud máxima del correo (columna usuarios.correo).
LONGITUD_MAXIMA_CORREO = 180


def obtener_cuerpo_json() -> dict:
    """Lee el cuerpo JSON de la petición y garantiza que sea un objeto.

    - Sin cuerpo, o con JSON ilegible: devuelve {} (cada endpoint responderá
      con sus errores de campos obligatorios).
    - Con un JSON que no es un objeto (arreglo, número, texto...): 422.
    """
    datos = request.get_json(silent=True)
    if datos is None:
        return {}
    if not isinstance(datos, dict):
        raise ErrorAPI("CUERPO_INVALIDO",
                       "El cuerpo de la petición debe ser un objeto JSON.", 422)
    return datos


def texto(valor, campo: str, obligatorio: bool = False,
          maximo: int | None = None) -> str | None:
    """Valida un campo de texto y lo devuelve sin espacios en los extremos.

    - Ausente o vacío: devuelve None (o 422 CAMPOS_REQUERIDOS si es obligatorio).
    - Que no sea texto (número, lista, objeto...): 422 CAMPO_INVALIDO.
    - Más largo que `maximo`: 422 CAMPO_INVALIDO (evita desbordar la columna).
    """
    if valor is None:
        limpio = ""
    elif isinstance(valor, str):
        limpio = valor.strip()
    else:
        raise ErrorAPI("CAMPO_INVALIDO",
                       f"El campo '{campo}' debe ser texto.", 422)

    if not limpio:
        if obligatorio:
            raise ErrorAPI("CAMPOS_REQUERIDOS",
                           f"Faltan campos obligatorios: {campo}.", 422)
        return None
    if maximo is not None and len(limpio) > maximo:
        raise ErrorAPI(
            "CAMPO_INVALIDO",
            f"El campo '{campo}' no puede superar {maximo} caracteres.", 422)
    return limpio


def booleano(valor, campo: str) -> bool:
    """Valida que el valor sea true/false (no se aceptan 0, 1 ni textos)."""
    if not isinstance(valor, bool):
        raise ErrorAPI("CAMPO_INVALIDO",
                       f"El campo '{campo}' debe ser verdadero o falso.", 422)
    return valor


def validar_id(valor, campo: str, codigo: str = "ID_INVALIDO") -> int:
    """Valida un identificador: entero positivo que cabe en una columna integer."""
    if isinstance(valor, bool) or not isinstance(valor, int) \
            or valor < 1 or valor > ID_MAXIMO:
        raise ErrorAPI(
            codigo, f"El campo '{campo}' debe ser un entero positivo.", 422)
    return valor


def normalizar_correo(correo: str) -> str:
    """Normaliza un correo: quita espacios y lo pasa a minúsculas."""
    return (correo or "").strip().lower()


def validar_correo(correo) -> str:
    """Normaliza y valida el formato de un correo. Devuelve el correo limpio.

    Lanza ErrorAPI(422) si no es texto, está vacío o tiene formato inválido.
    """
    if correo is not None and not isinstance(correo, str):
        raise ErrorAPI("CORREO_INVALIDO", "El correo debe ser texto.", 422)
    correo_limpio = normalizar_correo(correo)
    if not correo_limpio:
        raise ErrorAPI("CORREO_REQUERIDO", "El correo es obligatorio.", 422)
    if (len(correo_limpio) > LONGITUD_MAXIMA_CORREO
            or not _PATRON_CORREO.match(correo_limpio)):
        raise ErrorAPI("CORREO_INVALIDO",
                       "El formato del correo no es válido.", 422)
    return correo_limpio


def validar_password(password) -> str:
    """Valida la contraseña (texto, largo mínimo y máximo). La devuelve.

    Lanza ErrorAPI(422) si falta, no es texto, es demasiado corta o demasiado larga.
    """
    if password is not None and not isinstance(password, str):
        raise ErrorAPI("PASSWORD_INVALIDA", "La contraseña debe ser texto.", 422)
    if not password:
        raise ErrorAPI("PASSWORD_REQUERIDA", "La contraseña es obligatoria.", 422)
    if len(password) < LONGITUD_MINIMA_PASSWORD:
        raise ErrorAPI(
            "PASSWORD_CORTA",
            f"La contraseña debe tener al menos {LONGITUD_MINIMA_PASSWORD} "
            "caracteres.",
            422,
        )
    if len(password.encode("utf-8")) > LONGITUD_MAXIMA_PASSWORD_BYTES:
        raise ErrorAPI(
            "PASSWORD_LARGA",
            f"La contraseña no puede superar {LONGITUD_MAXIMA_PASSWORD_BYTES} "
            "caracteres.",
            422,
        )
    return password


def validar_entero_en_rango(valor, nombre: str, minimo: int, maximo: int,
                            codigo: str = "VALOR_INVALIDO") -> int:
    """Valida que `valor` sea un entero dentro de [minimo, maximo].

    Devuelve el entero. Lanza ErrorAPI(422) si no es entero o está fuera de
    rango. `nombre` se usa para el mensaje; `codigo` para el error.
    """
    # Rechazamos booleanos (en Python bool es subclase de int) y no enteros.
    if isinstance(valor, bool) or not isinstance(valor, int):
        # Permitimos cadenas numéricas ("12"), pero no decimales.
        try:
            if isinstance(valor, str) and valor.strip().lstrip("-").isdigit():
                valor = int(valor.strip())
            else:
                raise ValueError
        except (ValueError, TypeError):
            raise ErrorAPI(codigo, f"El campo '{nombre}' debe ser un entero.", 422)

    if valor < minimo or valor > maximo:
        raise ErrorAPI(
            codigo,
            f"El campo '{nombre}' debe estar entre {minimo} y {maximo}.",
            422,
        )
    return valor


def requerir_campos(datos: dict, campos: list[str]) -> None:
    """Verifica que los campos obligatorios estén presentes y no vacíos.

    Lanza ErrorAPI(422) indicando cuáles faltan.
    """
    if not isinstance(datos, dict):
        raise ErrorAPI("CUERPO_INVALIDO",
                       "El cuerpo de la petición debe ser un objeto JSON.", 422)
    faltantes = [c for c in campos
                 if datos.get(c) is None or str(datos.get(c)).strip() == ""]
    if faltantes:
        raise ErrorAPI(
            "CAMPOS_REQUERIDOS",
            f"Faltan campos obligatorios: {', '.join(faltantes)}.",
            422,
        )
