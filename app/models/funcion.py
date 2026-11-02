"""Modelo Funcion: proyección de una película en una sala a una hora dada."""

from sqlalchemy import Enum as SAEnum

from app.extensions import db
from app.models.enums import EstadoFuncion


class Funcion(db.Model):
    """Una función (proyección) concreta.

    `inicio` se guarda en UTC (timestamptz). `precio` es un entero en pesos
    colombianos (COP), sin decimales.
    """

    __tablename__ = "funciones"

    id = db.Column(db.Integer, primary_key=True)
    pelicula_id = db.Column(
        db.Integer, db.ForeignKey("peliculas.id"), nullable=False, index=True
    )
    sala_id = db.Column(
        db.Integer, db.ForeignKey("salas.id"), nullable=False, index=True
    )
    inicio = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    precio = db.Column(db.Integer, nullable=False)
    estado = db.Column(
        SAEnum(EstadoFuncion, name="estado_funcion",
               values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=EstadoFuncion.ACTIVA,
        index=True,
    )

    pelicula = db.relationship("Pelicula", back_populates="funciones")
    sala = db.relationship("Sala", back_populates="funciones")
    asientos = db.relationship(
        "AsientoFuncion", back_populates="funcion",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Funcion {self.id} pelicula={self.pelicula_id} {self.inicio}>"
