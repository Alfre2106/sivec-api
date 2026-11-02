"""Modelo Validacion: registro de CADA intento de validar una entrada.

Se registran todos los intentos (válidos o no) para auditoría y reportes.
`entrada_id` es nullable porque un código inválido puede no corresponder a
ninguna entrada.
"""

from sqlalchemy import Enum as SAEnum

from app.extensions import db
from app.models.enums import ResultadoValidacion
from app.utils.tiempo import ahora_utc


class Validacion(db.Model):
    """Un intento de validación de entrada en taquilla."""

    __tablename__ = "validaciones"

    id = db.Column(db.Integer, primary_key=True)
    entrada_id = db.Column(
        db.Integer, db.ForeignKey("entradas.id"), nullable=True, index=True
    )
    codigo_leido = db.Column(db.String(40), nullable=False, index=True)
    taquillero_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True
    )
    fecha = db.Column(db.DateTime(timezone=True), nullable=False,
                      default=ahora_utc)
    resultado = db.Column(
        SAEnum(ResultadoValidacion, name="resultado_validacion",
               values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        index=True,
    )
    detalle = db.Column(db.String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<Validacion {self.id} {self.codigo_leido} ({self.resultado.value})>"
