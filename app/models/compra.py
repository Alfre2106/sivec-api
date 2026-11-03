"""Modelo Compra: operación de venta de una o varias entradas (RN-05)."""

from sqlalchemy import Enum as SAEnum

from app.extensions import db
from app.models.enums import EstadoPago
from app.utils.tiempo import ahora_utc


class Compra(db.Model):
    """Una compra registrada.

    `usuario_id` es quién registró la compra (el cliente desde su cuenta, o el
    taquillero en una venta en taquilla). `total` es un entero en COP.
    """

    __tablename__ = "compras"

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(
        db.Integer, db.ForeignKey("clientes.id"), nullable=False, index=True
    )
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True
    )
    funcion_id = db.Column(
        db.Integer, db.ForeignKey("funciones.id"), nullable=False, index=True
    )
    total = db.Column(db.Integer, nullable=False)
    metodo_pago = db.Column(db.String(40), nullable=True)
    estado_pago = db.Column(
        SAEnum(EstadoPago, name="estado_pago",
               values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        index=True,
    )
    creado_en = db.Column(db.DateTime(timezone=True), nullable=False,
                          default=ahora_utc)

    cliente = db.relationship("Cliente", back_populates="compras")
    entradas = db.relationship("Entrada", back_populates="compra")
    # Relación de solo lectura hacia la función (sin cambiar el esquema).
    funcion = db.relationship("Funcion")

    def __repr__(self) -> str:
        return f"<Compra {self.id} total={self.total} ({self.estado_pago.value})>"
