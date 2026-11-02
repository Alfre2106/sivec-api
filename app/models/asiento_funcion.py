"""Modelo AsientoFuncion: cada asiento concreto de una función.

Los asientos se generan al crear la función (todos en estado "disponible").
La restricción UNIQUE (funcion_id, fila, numero) es la segunda defensa contra
ventas duplicadas en condiciones de concurrencia (CA-10).
"""

from sqlalchemy import Enum as SAEnum, UniqueConstraint

from app.extensions import db
from app.models.enums import EstadoAsiento


class AsientoFuncion(db.Model):
    """Un asiento físico asociado a una función concreta."""

    __tablename__ = "asientos_funcion"
    __table_args__ = (
        # Un asiento (fila+numero) no puede repetirse dentro de una función.
        UniqueConstraint("funcion_id", "fila", "numero",
                         name="uq_asiento_funcion_fila_numero"),
    )

    id = db.Column(db.Integer, primary_key=True)
    funcion_id = db.Column(
        db.Integer, db.ForeignKey("funciones.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    fila = db.Column(db.String(2), nullable=False)      # letra de fila (A, B, ...)
    numero = db.Column(db.Integer, nullable=False)       # número dentro de la fila
    estado = db.Column(
        SAEnum(EstadoAsiento, name="estado_asiento",
               values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=EstadoAsiento.DISPONIBLE,
        index=True,
    )

    funcion = db.relationship("Funcion", back_populates="asientos")
    reservas = db.relationship("Reserva", back_populates="asiento")

    def __repr__(self) -> str:
        return f"<AsientoFuncion {self.fila}{self.numero} ({self.estado.value})>"
