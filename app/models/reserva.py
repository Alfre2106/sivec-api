"""Modelo Reserva: bloqueo temporal de un asiento por un usuario (RN-03)."""

from sqlalchemy import Enum as SAEnum

from app.extensions import db
from app.models.enums import EstadoReserva
from app.utils.tiempo import ahora_utc


class Reserva(db.Model):
    """Reserva temporal de un asiento.

    Dura unos minutos (configurable en .env). Al vencer (`vence_en`), el
    asiento vuelve a disponible, ya sea por el scheduler o por expiración
    perezosa al consultar.
    """

    __tablename__ = "reservas"

    id = db.Column(db.Integer, primary_key=True)
    asiento_id = db.Column(
        db.Integer, db.ForeignKey("asientos_funcion.id"),
        nullable=False, index=True
    )
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True
    )
    reservado_en = db.Column(db.DateTime(timezone=True), nullable=False,
                             default=ahora_utc)
    vence_en = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    estado = db.Column(
        SAEnum(EstadoReserva, name="estado_reserva",
               values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=EstadoReserva.ACTIVA,
        index=True,
    )

    asiento = db.relationship("AsientoFuncion", back_populates="reservas")

    def __repr__(self) -> str:
        return f"<Reserva {self.id} asiento={self.asiento_id} ({self.estado.value})>"
