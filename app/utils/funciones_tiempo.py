"""Helpers de tiempo y estado para funciones.

El "estado efectivo" se calcula al vuelo (no se persiste): una función activa
cuya hora de fin ya pasó se considera FINALIZADA. Esto se reutilizará en la
Fase B4 para RN-08 (no reservar ni vender en funciones iniciadas/finalizadas).
"""

from datetime import timedelta

from app.models.enums import EstadoFuncion
from app.utils.tiempo import ahora_utc


def hora_fin(funcion) -> "datetime":
    """Devuelve la hora de fin = inicio + duracion de la película.

    Si la película no tiene duración registrada, se asume 0 (fin = inicio).
    """
    duracion = funcion.pelicula.duracion_min if funcion.pelicula else None
    minutos = duracion or 0
    return funcion.inicio + timedelta(minutes=minutos)


def funcion_ya_inicio(funcion) -> bool:
    """True si la hora de inicio de la función ya pasó."""
    return funcion.inicio <= ahora_utc()


def funcion_ya_termino(funcion) -> bool:
    """True si la hora de fin de la función ya pasó."""
    return hora_fin(funcion) <= ahora_utc()


def estado_efectivo(funcion) -> EstadoFuncion:
    """Calcula el estado efectivo de la función sin modificar la base de datos.

    - Si está cancelada, sigue cancelada.
    - Si está activa pero su hora de fin ya pasó, se considera finalizada.
    - En otro caso, conserva su estado almacenado.
    """
    if funcion.estado == EstadoFuncion.CANCELADA:
        return EstadoFuncion.CANCELADA
    if funcion.estado == EstadoFuncion.ACTIVA and funcion_ya_termino(funcion):
        return EstadoFuncion.FINALIZADA
    return funcion.estado
