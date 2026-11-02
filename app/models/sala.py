"""Modelo Sala: espacio físico con una distribución de asientos."""

from app.extensions import db


class Sala(db.Model):
    """Sala de proyección.

    La capacidad se deriva de filas * asientos_por_fila, pero se guarda
    también como columna para consultas rápidas y para dejarla explícita.
    """

    __tablename__ = "salas"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(80), nullable=False)
    filas = db.Column(db.Integer, nullable=False)
    asientos_por_fila = db.Column(db.Integer, nullable=False)
    capacidad = db.Column(db.Integer, nullable=False)

    funciones = db.relationship("Funcion", back_populates="sala")

    def __repr__(self) -> str:
        return f"<Sala {self.id} {self.nombre}>"
