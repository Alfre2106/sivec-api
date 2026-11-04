"""Autorización por roles.

Expone el decorador `@rol_requerido(...)` para proteger endpoints y helpers
para obtener el usuario autenticado desde el token JWT. Los permisos se
validan SIEMPRE en el servidor (RNF-10).
"""

from functools import wraps

from flask_jwt_extended import verify_jwt_in_request, get_jwt, get_jwt_identity

from app.utils.errores import ErrorAPI


def rol_requerido(*roles_permitidos):
    """Decorador que exige un token válido y uno de los roles indicados.

    Uso:
        @rol_requerido("administrador")
        def crear_usuario(): ...

    - Sin token / token inválido o vencido -> 401 (lo gestionan los handlers
      de JWT con el formato uniforme).
    - Rol no permitido -> 403 con código ROL_NO_AUTORIZADO.
    """
    def decorador(funcion):
        @wraps(funcion)
        def envoltura(*args, **kwargs):
            # Exige y valida el token; si falla, Flask-JWT-Extended dispara
            # el handler correspondiente (401).
            verify_jwt_in_request()
            claims = get_jwt()
            rol_actual = claims.get("rol")
            if roles_permitidos and rol_actual not in roles_permitidos:
                raise ErrorAPI(
                    "ROL_NO_AUTORIZADO",
                    "No tienes permisos para realizar esta acción.",
                    403,
                )
            return funcion(*args, **kwargs)
        # Metadato consultable: permite a las pruebas y a la documentación
        # saber qué roles admite cada ruta sin leer el código de cada vista.
        # Tupla vacía = cualquier usuario autenticado.
        envoltura.roles_permitidos = tuple(roles_permitidos)
        return envoltura
    return decorador


def id_usuario_actual() -> int:
    """Devuelve el id (int) del usuario autenticado a partir del token."""
    return int(get_jwt_identity())


def rol_usuario_actual() -> str:
    """Devuelve el rol del usuario autenticado a partir de los claims."""
    return get_jwt().get("rol")
