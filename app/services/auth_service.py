"""Servicio de autenticación: registro, login y emisión de tokens.

Contiene la lógica de negocio; las rutas solo reciben la petición y delegan
aquí. Las contraseñas se manejan siempre con bcrypt y nunca se exponen.
"""

from flask_jwt_extended import create_access_token

from app.extensions import db
from app.models.usuario import Usuario
from app.models.cliente import Cliente
from app.models.enums import RolUsuario
from app.services.auditoria_service import registrar_auditoria
from app.utils.errores import ErrorAPI
from app.utils.seguridad import hashear_password, verificar_password
from app.utils.validaciones import validar_correo, validar_password


def _emitir_token(usuario: Usuario) -> str:
    """Crea un token JWT con el rol del usuario en los claims.

    La identidad es el id del usuario (como cadena) y se añade el rol como
    claim adicional para la autorización. La expiración la define el .env.
    """
    return create_access_token(
        identity=str(usuario.id),
        additional_claims={"rol": usuario.rol.value},
    )


def registrar_cliente(datos: dict) -> tuple[str, Usuario]:
    """Registra un nuevo usuario con rol cliente y su ficha en `clientes`.

    El registro público SOLO crea clientes. Devuelve (token, usuario).
    Lanza ErrorAPI(409) si el correo ya está registrado.
    """
    correo = validar_correo(datos.get("correo"))
    password = validar_password(datos.get("password"))
    nombre = (datos.get("nombre") or "").strip()

    # Correo único: segunda defensa además de la restricción UNIQUE en BD.
    if Usuario.query.filter_by(correo=correo).first():
        raise ErrorAPI("CORREO_YA_REGISTRADO",
                       "El correo ya está registrado.", 409)

    # Creamos el usuario (rol cliente, siempre) y su ficha de cliente.
    usuario = Usuario(
        nombre=nombre,
        correo=correo,
        password_hash=hashear_password(password),
        rol=RolUsuario.CLIENTE,
        activo=True,
    )
    db.session.add(usuario)
    db.session.flush()  # necesitamos el id del usuario

    cliente = Cliente(
        usuario_id=usuario.id,
        nombre=nombre,
        documento=(datos.get("documento") or None),
        contacto=(datos.get("contacto") or None),
    )
    db.session.add(cliente)

    # Auditoría del registro (sin datos sensibles).
    registrar_auditoria(
        usuario_id=usuario.id,
        accion="registro",
        entidad="usuarios",
        entidad_id=usuario.id,
        detalle={"correo": correo},
    )

    db.session.commit()
    return _emitir_token(usuario), usuario


def iniciar_sesion(datos: dict) -> tuple[str, Usuario]:
    """Valida credenciales y devuelve (token, usuario).

    Usa un mensaje genérico (401) tanto si el correo no existe como si la
    contraseña es incorrecta, para no revelar qué correos están registrados.
    Un usuario inactivo no puede iniciar sesión.
    """
    correo = (datos.get("correo") or "").strip().lower()
    password = datos.get("password") or ""

    usuario = Usuario.query.filter_by(correo=correo).first()

    # Mensaje genérico unificado para cualquier fallo de credenciales.
    credenciales_invalidas = ErrorAPI(
        "CREDENCIALES_INVALIDAS", "Correo o contraseña incorrectos.", 401)

    if usuario is None or not verificar_password(password, usuario.password_hash):
        # Auditamos el intento fallido SIN guardar la contraseña.
        registrar_auditoria(
            usuario_id=usuario.id if usuario else None,
            accion="login_fallido",
            entidad="usuarios",
            entidad_id=usuario.id if usuario else None,
            detalle={"correo": correo},
        )
        db.session.commit()
        raise credenciales_invalidas

    if not usuario.activo:
        registrar_auditoria(
            usuario_id=usuario.id,
            accion="login_fallido",
            entidad="usuarios",
            entidad_id=usuario.id,
            detalle={"correo": correo, "motivo": "usuario_inactivo"},
        )
        db.session.commit()
        raise ErrorAPI("USUARIO_INACTIVO",
                       "La cuenta está desactivada.", 401)

    # Login correcto: auditamos el éxito.
    registrar_auditoria(
        usuario_id=usuario.id,
        accion="login_exitoso",
        entidad="usuarios",
        entidad_id=usuario.id,
        detalle={"correo": correo},
    )
    db.session.commit()
    return _emitir_token(usuario), usuario
