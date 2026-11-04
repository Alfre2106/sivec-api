"""Servicio de gestión de usuarios (operaciones de administrador).

Taquilleros y administradores SOLO se crean aquí. El registro público crea
clientes (ver auth_service). Todas las acciones se auditan.
"""

from app.extensions import db
from app.models.usuario import Usuario
from app.models.enums import RolUsuario
from app.services.auditoria_service import registrar_auditoria
from app.utils.errores import ErrorAPI
from app.utils.seguridad import hashear_password
from app.utils.validaciones import (
    booleano, texto, validar_correo, validar_password,
)

# Roles que un administrador puede crear por este medio.
ROLES_CREABLES = {RolUsuario.TAQUILLERO.value, RolUsuario.ADMINISTRADOR.value}


def _parsear_rol(valor: str) -> RolUsuario:
    """Convierte una cadena de rol en el Enum, o lanza 422 si no es válida."""
    try:
        return RolUsuario(valor)
    except ValueError:
        validos = ", ".join(r.value for r in RolUsuario)
        raise ErrorAPI("ROL_INVALIDO",
                       f"Rol no válido. Valores permitidos: {validos}.", 422)


def listar_usuarios(rol: str | None = None) -> list[Usuario]:
    """Lista los usuarios, opcionalmente filtrando por rol."""
    consulta = Usuario.query
    if rol:
        consulta = consulta.filter_by(rol=_parsear_rol(rol))
    return consulta.order_by(Usuario.id).all()


def obtener_usuario(usuario_id: int) -> Usuario:
    """Obtiene un usuario por id o lanza 404."""
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None:
        raise ErrorAPI("USUARIO_NO_ENCONTRADO", "El usuario no existe.", 404)
    return usuario


def crear_usuario(datos: dict, admin_id: int) -> Usuario:
    """Crea un usuario con rol taquillero o administrador.

    No permite crear clientes por esta vía (esos van por el registro público).
    """
    correo = validar_correo(datos.get("correo"))
    password = validar_password(datos.get("password"))
    nombre = texto(datos.get("nombre"), "nombre", obligatorio=True, maximo=120)
    rol_texto = texto(datos.get("rol"), "rol", obligatorio=True, maximo=30)

    rol = _parsear_rol(rol_texto)
    if rol.value not in ROLES_CREABLES:
        raise ErrorAPI(
            "ROL_NO_PERMITIDO",
            "Por esta vía solo se pueden crear taquilleros o administradores.",
            422,
        )

    if Usuario.query.filter_by(correo=correo).first():
        raise ErrorAPI("CORREO_YA_REGISTRADO",
                       "El correo ya está registrado.", 409)

    usuario = Usuario(
        nombre=nombre,
        correo=correo,
        password_hash=hashear_password(password),
        rol=rol,
        activo=True,
    )
    db.session.add(usuario)
    db.session.flush()

    registrar_auditoria(
        usuario_id=admin_id,
        accion="crear_usuario",
        entidad="usuarios",
        entidad_id=usuario.id,
        detalle={"correo": correo, "rol": rol.value},
    )
    db.session.commit()
    return usuario


def editar_usuario(usuario_id: int, datos: dict, admin_id: int) -> Usuario:
    """Edita campos de un usuario (nombre, correo, rol, password, activo)."""
    usuario = obtener_usuario(usuario_id)
    cambios = {}

    if "nombre" in datos and datos["nombre"] is not None:
        nombre = texto(datos["nombre"], "nombre", maximo=120)
        if nombre:
            usuario.nombre = nombre
            cambios["nombre"] = nombre

    if "correo" in datos and datos["correo"] is not None:
        nuevo_correo = validar_correo(datos["correo"])
        # Evitar colisión con el correo de otro usuario.
        existente = Usuario.query.filter_by(correo=nuevo_correo).first()
        if existente and existente.id != usuario.id:
            raise ErrorAPI("CORREO_YA_REGISTRADO",
                           "El correo ya está registrado.", 409)
        usuario.correo = nuevo_correo
        cambios["correo"] = nuevo_correo

    if "rol" in datos and datos["rol"] is not None:
        rol = _parsear_rol(texto(datos["rol"], "rol", obligatorio=True, maximo=30))
        usuario.rol = rol
        cambios["rol"] = rol.value

    if "password" in datos and datos["password"] is not None:
        password = validar_password(datos["password"])
        usuario.password_hash = hashear_password(password)
        cambios["password"] = "actualizada"  # nunca guardamos el valor real

    if "activo" in datos and datos["activo"] is not None:
        usuario.activo = booleano(datos["activo"], "activo")
        cambios["activo"] = usuario.activo

    registrar_auditoria(
        usuario_id=admin_id,
        accion="editar_usuario",
        entidad="usuarios",
        entidad_id=usuario.id,
        detalle={"cambios": cambios},
    )
    db.session.commit()
    return usuario


def desactivar_usuario(usuario_id: int, admin_id: int) -> Usuario:
    """Desactiva un usuario (no lo borra). Un inactivo no puede iniciar sesión."""
    usuario = obtener_usuario(usuario_id)
    usuario.activo = False

    registrar_auditoria(
        usuario_id=admin_id,
        accion="desactivar_usuario",
        entidad="usuarios",
        entidad_id=usuario.id,
        detalle={"correo": usuario.correo},
    )
    db.session.commit()
    return usuario
