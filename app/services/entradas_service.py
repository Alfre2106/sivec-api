"""Servicio de entradas: detalle, QR y control de permisos de acceso."""

import io

import qrcode

from app.extensions import db
from app.models.entrada import Entrada
from app.models.compra import Compra
from app.models.cliente import Cliente
from app.models.usuario import Usuario
from app.models.enums import RolUsuario
from app.utils.errores import ErrorAPI


def obtener_entrada(entrada_id: int) -> Entrada:
    """Obtiene una entrada por id o lanza 404."""
    entrada = db.session.get(Entrada, entrada_id)
    if entrada is None:
        raise ErrorAPI("ENTRADA_NO_ENCONTRADA", "La entrada no existe.", 404)
    return entrada


def verificar_acceso_entrada(entrada: Entrada, usuario_id: int) -> None:
    """Valida que el usuario pueda ver/usar la entrada (RN-12).

    Permiten acceso: el cliente dueño de la entrada, cualquier taquillero y el
    administrador. Otro cliente recibe 403.
    """
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None:
        raise ErrorAPI("USUARIO_NO_ENCONTRADO", "El usuario no existe.", 404)

    # Taquillero y administrador tienen acceso a cualquier entrada.
    if usuario.rol in (RolUsuario.TAQUILLERO, RolUsuario.ADMINISTRADOR):
        return

    # Cliente: solo si la compra está ligada a su propio registro de cliente.
    compra = db.session.get(Compra, entrada.compra_id)
    cliente = Cliente.query.filter_by(usuario_id=usuario_id).first()
    if compra is None or cliente is None or compra.cliente_id != cliente.id:
        raise ErrorAPI(
            "ENTRADA_AJENA",
            "No tienes permiso para acceder a esta entrada.", 403)


def generar_qr_png(texto: str) -> bytes:
    """Genera la imagen PNG (bytes) del código QR del texto dado."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(texto)
    qr.make(fit=True)
    imagen = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    imagen.save(buffer, format="PNG")
    return buffer.getvalue()
