"""Modelo Auditoria: traza de acciones sensibles (compras, validaciones, etc.)."""

from sqlalchemy.dialects.postgresql import JSONB

from app.extensions import db
from app.utils.tiempo import ahora_utc


class Auditoria(db.Model):
    """Registro de auditoría de una acción realizada en el sistema.

    `detalle` se guarda como JSONB para poder almacenar datos variables de
    cada acción (identificadores, montos, etc.).
    """

    __tablename__ = "auditoria"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=True, index=True
    )
    accion = db.Column(db.String(80), nullable=False, index=True)
    entidad = db.Column(db.String(80), nullable=True)
    entidad_id = db.Column(db.Integer, nullable=True)
    detalle = db.Column(JSONB, nullable=True)
    fecha = db.Column(db.DateTime(timezone=True), nullable=False,
                      default=ahora_utc, index=True)

    def __repr__(self) -> str:
        return f"<Auditoria {self.id} {self.accion}>"
