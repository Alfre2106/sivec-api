"""Modelos de datos de SIVEC.

Importamos aquí todas las entidades para que queden registradas en el
metadata de SQLAlchemy y Flask-Migrate pueda detectarlas al generar las
migraciones. El orden respeta en lo posible las dependencias de FK.
"""

from app.models.usuario import Usuario
from app.models.cliente import Cliente
from app.models.pelicula import Pelicula
from app.models.sala import Sala
from app.models.funcion import Funcion
from app.models.asiento_funcion import AsientoFuncion
from app.models.reserva import Reserva
from app.models.compra import Compra
from app.models.entrada import Entrada
from app.models.validacion import Validacion
from app.models.auditoria import Auditoria

__all__ = [
    "Usuario",
    "Cliente",
    "Pelicula",
    "Sala",
    "Funcion",
    "AsientoFuncion",
    "Reserva",
    "Compra",
    "Entrada",
    "Validacion",
    "Auditoria",
]
