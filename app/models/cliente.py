"""Modelo Cliente: persona que compra entradas.

Un cliente puede existir sin cuenta de usuario (venta en taquilla): por eso
usuario_id es nullable.
"""

from app.extensions import db


class Cliente(db.Model):
    """Datos de un cliente, con o sin cuenta de usuario asociada."""

    __tablename__ = "clientes"

    id = db.Column(db.Integer, primary_key=True)
    # Puede ser nulo: cliente sin cuenta, atendido en taquilla.
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuarios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    nombre = db.Column(db.String(120), nullable=False)
    documento = db.Column(db.String(40), nullable=True)
    contacto = db.Column(db.String(120), nullable=True)

    usuario = db.relationship("Usuario", back_populates="cliente")
    compras = db.relationship("Compra", back_populates="cliente")

    def __repr__(self) -> str:
        return f"<Cliente {self.id} {self.nombre}>"
