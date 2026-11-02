"""Servicio de auditoría.

Centraliza el registro de acciones sensibles (registro, login, gestión de
usuarios, compras, validaciones, cancelaciones...). Nunca debe guardar datos
sensibles como contraseñas.
"""

from app.extensions import db
from app.models.auditoria import Auditoria


def registrar_auditoria(usuario_id, accion, entidad=None, entidad_id=None,
                        detalle=None):
    """Registra una acción en la tabla de auditoría.

    Args:
        usuario_id: id del usuario que ejecuta la acción (puede ser None).
        accion: nombre corto de la acción, ej. "login_exitoso".
        entidad: nombre de la entidad afectada, ej. "usuarios".
        entidad_id: id de la entidad afectada (opcional).
        detalle: diccionario con datos adicionales (se guarda como JSONB).
                 NUNCA incluir contraseñas ni hashes.

    El registro se añade a la sesión; el commit lo hace quien llama (para que
    la auditoría viaje dentro de la misma transacción de la acción).
    """
    registro = Auditoria(
        usuario_id=usuario_id,
        accion=accion,
        entidad=entidad,
        entidad_id=entidad_id,
        detalle=detalle,
    )
    db.session.add(registro)
    return registro
