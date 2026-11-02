"""Modelo Pelicula: catálogo de películas que se proyectan."""

from app.extensions import db


class Pelicula(db.Model):
    """Una película del catálogo."""

    __tablename__ = "peliculas"

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(180), nullable=False)
    genero = db.Column(db.String(80), nullable=True)
    clasificacion = db.Column(db.String(20), nullable=True)
    duracion_min = db.Column(db.Integer, nullable=True)
    sinopsis = db.Column(db.Text, nullable=True)
    poster_url = db.Column(db.String(255), nullable=True)
    activa = db.Column(db.Boolean, nullable=False, default=True)

    funciones = db.relationship("Funcion", back_populates="pelicula")

    def __repr__(self) -> str:
        return f"<Pelicula {self.id} {self.titulo}>"
