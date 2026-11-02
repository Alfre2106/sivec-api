"""Serializadores: convierten modelos en diccionarios listos para JSON.

Regla crítica: NUNCA incluir `password_hash` ni otros datos sensibles.
"""

from app.models.cliente import Cliente


def serializar_usuario(usuario, incluir_cliente_id=True):
    """Serializa un usuario a dict seguro (sin password_hash).

    Si `incluir_cliente_id` es True, añade el id del cliente asociado (o None).
    """
    datos = {
        "id": usuario.id,
        "nombre": usuario.nombre,
        "correo": usuario.correo,
        "rol": usuario.rol.value,
        "activo": usuario.activo,
        "creado_en": usuario.creado_en.isoformat() if usuario.creado_en else None,
    }
    if incluir_cliente_id:
        cliente = Cliente.query.filter_by(usuario_id=usuario.id).first()
        datos["cliente_id"] = cliente.id if cliente else None
    return datos
