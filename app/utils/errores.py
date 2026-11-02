"""Manejo uniforme de errores de la API.

Todos los errores se devuelven con la misma forma:

    {"error": {"codigo": "CODIGO_ERROR", "mensaje": "Texto en español"}}

Se define una excepción propia (`ErrorAPI`) que los servicios pueden lanzar,
y se registran manejadores globales para producir siempre JSON (incluso para
errores HTTP estándar como 404 o 405).
"""

from flask import jsonify
from werkzeug.exceptions import HTTPException


class ErrorAPI(Exception):
    """Excepción de negocio controlada.

    Permite a los servicios y rutas lanzar un error con un código de dominio,
    un mensaje en español y un código HTTP concreto.

    Ejemplo:
        raise ErrorAPI("ASIENTO_NO_DISPONIBLE",
                       "El asiento ya no está disponible", 409)
    """

    def __init__(self, codigo: str, mensaje: str, http_status: int = 400,
                 detalle: dict | None = None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.http_status = http_status
        # Información extra opcional (por ejemplo, la lista de asientos en conflicto)
        self.detalle = detalle or {}

    def to_dict(self) -> dict:
        """Convierte la excepción en el cuerpo JSON de respuesta."""
        cuerpo = {"error": {"codigo": self.codigo, "mensaje": self.mensaje}}
        if self.detalle:
            cuerpo["error"]["detalle"] = self.detalle
        return cuerpo


def _respuesta_error(codigo: str, mensaje: str, http_status: int):
    """Construye una respuesta JSON de error con el formato estándar."""
    respuesta = jsonify({"error": {"codigo": codigo, "mensaje": mensaje}})
    respuesta.status_code = http_status
    return respuesta


def registrar_manejadores_errores(app):
    """Registra los manejadores globales de errores en la app."""

    @app.errorhandler(ErrorAPI)
    def manejar_error_api(error: ErrorAPI):
        """Errores de negocio controlados."""
        respuesta = jsonify(error.to_dict())
        respuesta.status_code = error.http_status
        return respuesta

    @app.errorhandler(HTTPException)
    def manejar_error_http(error: HTTPException):
        """Errores HTTP estándar (404, 405, etc.) en formato uniforme."""
        codigo = error.name.upper().replace(" ", "_")
        mensaje = error.description or "Ocurrió un error."
        return _respuesta_error(codigo, mensaje, error.code or 500)

    @app.errorhandler(Exception)
    def manejar_error_inesperado(error: Exception):
        """Cualquier otro error no previsto se devuelve como 500.

        En desarrollo se incluye el detalle para facilitar la depuración.
        """
        app.logger.exception("Error inesperado: %s", error)
        mensaje = "Ocurrió un error interno en el servidor."
        if app.config.get("DEBUG"):
            mensaje = f"{mensaje} Detalle: {error}"
        return _respuesta_error("ERROR_INTERNO", mensaje, 500)


def registrar_manejadores_jwt(jwt):
    """Registra los callbacks de error de Flask-JWT-Extended.

    Hace que los errores de autenticación usen el MISMO formato uniforme del
    proyecto. Token ausente, inválido o vencido devuelven 401.
    """

    @jwt.unauthorized_loader
    def falta_token(motivo):
        """No se envió el token (cabecera Authorization ausente)."""
        return _respuesta_error(
            "TOKEN_AUSENTE",
            "Se requiere autenticación para acceder a este recurso.", 401)

    @jwt.invalid_token_loader
    def token_invalido(motivo):
        """El token está mal formado o la firma no es válida."""
        return _respuesta_error(
            "TOKEN_INVALIDO", "El token de autenticación no es válido.", 401)

    @jwt.expired_token_loader
    def token_vencido(cabecera, payload):
        """El token expiró."""
        return _respuesta_error(
            "TOKEN_VENCIDO", "La sesión ha expirado. Inicia sesión de nuevo.",
            401)

    @jwt.revoked_token_loader
    def token_revocado(cabecera, payload):
        """El token fue revocado."""
        return _respuesta_error(
            "TOKEN_REVOCADO", "El token ha sido revocado.", 401)

    @jwt.needs_fresh_token_loader
    def token_no_fresco(cabecera, payload):
        """Se requiere un token 'fresh' que no se proporcionó."""
        return _respuesta_error(
            "TOKEN_NO_FRESCO", "Se requiere una autenticación reciente.", 401)
