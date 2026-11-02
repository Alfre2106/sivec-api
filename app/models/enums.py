"""Tipos ENUM de PostgreSQL usados por los modelos.

Se definen como clases Enum de Python y se reutilizan en los modelos mediante
SQLAlchemy Enum, que crea los tipos ENUM nativos en PostgreSQL. Centralizarlos
aquí evita repetir las cadenas y mantiene los estados consistentes.
"""

import enum


class RolUsuario(str, enum.Enum):
    """Roles posibles de un usuario del sistema."""
    CLIENTE = "cliente"
    TAQUILLERO = "taquillero"
    ADMINISTRADOR = "administrador"


class EstadoFuncion(str, enum.Enum):
    """Estado de una función de cine."""
    ACTIVA = "activa"
    CANCELADA = "cancelada"
    FINALIZADA = "finalizada"


class EstadoAsiento(str, enum.Enum):
    """Estado de un asiento dentro de una función (RN-01)."""
    DISPONIBLE = "disponible"
    RESERVADO = "reservado"
    VENDIDO = "vendido"


class EstadoReserva(str, enum.Enum):
    """Ciclo de vida de una reserva."""
    ACTIVA = "activa"
    EXPIRADA = "expirada"
    CONVERTIDA = "convertida"
    CANCELADA = "cancelada"


class EstadoPago(str, enum.Enum):
    """Resultado del pago simulado de una compra (RN-11)."""
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"


class EstadoEntrada(str, enum.Enum):
    """Estado de una entrada emitida."""
    ACTIVA = "activa"
    USADA = "usada"
    ANULADA = "anulada"


class ResultadoValidacion(str, enum.Enum):
    """Resultado de un intento de validación de una entrada."""
    VALIDA = "valida"
    YA_USADA = "ya_usada"
    INVALIDA = "invalida"
    OTRA_FUNCION = "otra_funcion"
    ANULADA = "anulada"
