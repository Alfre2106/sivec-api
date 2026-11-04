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
    # Seguridad: los errores de SQL no incluyen los valores de los parámetros.
    # Así un fallo al guardar un usuario nunca deja un password_hash en un log
    # ni en la respuesta de error (en modo debug).
    SQLALCHEMY_ENGINE_OPTIONS = {"hide_parameters": True}

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
    # Minutos de anticipación con los que se acepta validar una entrada
    # antes del inicio de la función (ventana de validación en puerta).
    VALIDACION_ANTICIPACION_MINUTOS = int(
        os.getenv("VALIDACION_ANTICIPACION_MINUTOS", "120"))


class ConfiguracionDesarrollo(ConfiguracionBase):
    """Entorno de desarrollo local."""

    DEBUG = True


class ConfiguracionPruebas(ConfiguracionBase):
    """Entorno de pruebas automáticas (pytest)."""

    TESTING = True
    DEBUG = True
    # Las pruebas usan SIEMPRE su propia base (TEST_DATABASE_URL). No hay
    # valor de respaldo: si falta, create_app se niega a arrancar en "testing"
    # para que nunca se toque la base de desarrollo por accidente.
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL")


class ConfiguracionProduccion(ConfiguracionBase):
    """Entorno de producción."""

    DEBUG = False


# Mapa de nombre de entorno -> clase de configuración
CONFIGURACIONES = {
    "development": ConfiguracionDesarrollo,
    "testing": ConfiguracionPruebas,
    "production": ConfiguracionProduccion,
}


def nombre_base_datos(uri: str | None) -> str:
    """Devuelve el nombre de la base de datos de una URL de conexión."""
    if not uri:
        return ""
    return uri.rsplit("/", 1)[-1].split("?", 1)[0]


def validar_uri_pruebas(uri_pruebas: str | None) -> None:
    """Garantiza que las pruebas apuntan a una base distinta de la de trabajo.

    Reglas: TEST_DATABASE_URL debe estar definida, su base debe llamarse
    "*test*" y no puede ser la misma que DATABASE_URL. Lanza RuntimeError si
    alguna no se cumple (las pruebas borran datos, así que somos estrictos).
    """
    if not uri_pruebas:
        raise RuntimeError(
            "Falta TEST_DATABASE_URL. Las pruebas necesitan su propia base "
            "(por ejemplo .../sivec_test); defínela en el archivo .env."
        )
    base_pruebas = nombre_base_datos(uri_pruebas)
    if "test" not in base_pruebas.lower():
        raise RuntimeError(
            f"La base de pruebas '{base_pruebas}' debe llevar 'test' en el "
            "nombre (por ejemplo sivec_test). Se rechaza por seguridad."
        )
    if base_pruebas == nombre_base_datos(os.getenv("DATABASE_URL")):
        raise RuntimeError(
            "TEST_DATABASE_URL apunta a la misma base que DATABASE_URL. "
            "Las pruebas nunca deben usar la base de desarrollo."
        )


def validar_secretos_produccion(config) -> None:
    """En producción exige claves propias (no los valores de desarrollo)."""
    inseguras = {"clave-insegura-solo-dev", "clave-jwt-insegura-solo-dev",
                 "cambia-esta-clave-secreta", "cambia-esta-clave-jwt"}
    for nombre in ("SECRET_KEY", "JWT_SECRET_KEY"):
        if config.get(nombre) in inseguras or not config.get(nombre):
            raise RuntimeError(
                f"En producción {nombre} debe definirse en el .env con un "
                "valor largo y aleatorio."
            )


def obtener_configuracion(nombre_entorno: str | None = None):
    """Devuelve la clase de configuración según el entorno.

    Si no se pasa un nombre, usa la variable de entorno FLASK_ENV y,
    como último recurso, el entorno de desarrollo.
    """
    nombre = nombre_entorno or os.getenv("FLASK_ENV", "development")
    return CONFIGURACIONES.get(nombre, ConfiguracionDesarrollo)
