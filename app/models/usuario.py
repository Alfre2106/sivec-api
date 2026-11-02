"""Modelo Usuario: cuentas con acceso al sistema (cliente, taquillero, admin)."""

from sqlalchemy import Enum as SAEnum

from app.extensions import db
from app.models.enums import RolUsuario
from app.utils.tiempo import ahora_utc


class Usuario(db.Model):
    """Usuario con credenciales de acceso.

    La contraseña se guarda siempre como hash bcrypt (nunca en texto plano).
    El rol determina los permisos (se validan en el servidor, RNF-10).
    """

    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    # El correo es único y es el identificador de acceso.
    correo = db.Column(db.String(180), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(
        SAEnum(RolUsuario, name="rol_usuario",
               values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=RolUsuario.CLIENTE,
    )
    activo = db.Column(db.Boolean, nullable=False, default=True)
    creado_en = db.Column(db.DateTime(timezone=True), nullable=False,
                          default=ahora_utc)

    # Relaciones inversas
    cliente = db.relationship("Cliente", back_populates="usuario",
                              uselist=False)

    def __repr__(self) -> str:
        return f"<Usuario {self.id} {self.correo} ({self.rol.value})>"
