"""Modelo Entrada: boleto emitido para un asiento de una función (RN-06/07)."""

from sqlalchemy import Enum as SAEnum

from app.extensions import db
from app.models.enums import EstadoEntrada


class Entrada(db.Model):
    """Una entrada (boleto) con código único.

    El código es legible y único (segunda defensa con UNIQUE). Cada entrada
    solo vale para su función y su asiento, y se usa una sola vez.
    """

    __tablename__ = "entradas"

    id = db.Column(db.Integer, primary_key=True)
    # Código único legible, ej. "SIV-XXXXXXXXXXXX".
    codigo = db.Column(db.String(40), nullable=False, unique=True, index=True)
    compra_id = db.Column(
        db.Integer, db.ForeignKey("compras.id"), nullable=False, index=True
    )
    funcion_id = db.Column(
        db.Integer, db.ForeignKey("funciones.id"), nullable=False, index=True
    )
    asiento_id = db.Column(
        db.Integer, db.ForeignKey("asientos_funcion.id"),
        nullable=False, index=True
    )
    estado = db.Column(
        SAEnum(EstadoEntrada, name="estado_entrada",
               values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=EstadoEntrada.ACTIVA,
        index=True,
    )
    usada_en = db.Column(db.DateTime(timezone=True), nullable=True)

    compra = db.relationship("Compra", back_populates="entradas")

    def __repr__(self) -> str:
        return f"<Entrada {self.codigo} ({self.estado.value})>"
