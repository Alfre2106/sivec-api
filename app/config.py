"""Configuración de la aplicación SIVEC.

Las variables sensibles se leen desde el entorno (.env). Existe una clase por
cada entorno de ejecución: desarrollo, pruebas y producción.
"""

import os
from datetime import timedelta


class ConfiguracionBase:
    """Configuración común a todos los entornos."""

    # Clave secreta general de Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "clave-insegura-solo-dev")

    # --- Base de datos ---
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    # Desactivamos el seguimiento de modificaciones (ahorra memoria y evita avisos)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- JWT ---
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "clave-jwt-insegura-solo-dev")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.getenv("JWT_EXPIRACION_MINUTOS", "120"))
    )

    # --- CORS ---
    # Lista de orígenes permitidos para el frontend
    CORS_ORIGENES = [
        origen.strip()
        for origen in os.getenv("CORS_ORIGENES", "http://localhost:5173").split(",")
        if origen.strip()
    ]

    # --- Reglas de negocio ---
    RESERVA_DURACION_MINUTOS = int(os.getenv("RESERVA_DURACION_MINUTOS", "5"))
    ZONA_HORARIA = os.getenv("ZONA_HORARIA", "America/Bogota")
    # Máximo de asientos que se pueden reservar en una sola solicitud.
    MAX_ASIENTOS_POR_RESERVA = int(os.getenv("MAX_ASIENTOS_POR_RESERVA", "8"))
    # Máximo de reservas activas por usuario en una misma función.
    MAX_RESERVAS_ACTIVAS_POR_FUNCION = int(
        os.getenv("MAX_RESERVAS_ACTIVAS_POR_FUNCION", "8"))
    # Intervalo del job que expira reservas vencidas (segundos).
    SCHEDULER_INTERVALO_SEGUNDOS = int(
        os.getenv("SCHEDULER_INTERVALO_SEGUNDOS", "30"))


class ConfiguracionDesarrollo(ConfiguracionBase):
    """Entorno de desarrollo local."""

    DEBUG = True


class ConfiguracionPruebas(ConfiguracionBase):
    """Entorno de pruebas automáticas (pytest)."""

    TESTING = True
    DEBUG = True
    # Permite sobrescribir la BD con una de pruebas si se define
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL_TEST", os.getenv("DATABASE_URL")
    )


class ConfiguracionProduccion(ConfiguracionBase):
    """Entorno de producción."""

    DEBUG = False


# Mapa de nombre de entorno -> clase de configuración
CONFIGURACIONES = {
    "development": ConfiguracionDesarrollo,
    "testing": ConfiguracionPruebas,
    "production": ConfiguracionProduccion,
}


def obtener_configuracion(nombre_entorno: str | None = None):
    """Devuelve la clase de configuración según el entorno.

    Si no se pasa un nombre, usa la variable de entorno FLASK_ENV y,
    como último recurso, el entorno de desarrollo.
    """
    nombre = nombre_entorno or os.getenv("FLASK_ENV", "development")
    return CONFIGURACIONES.get(nombre, ConfiguracionDesarrollo)
