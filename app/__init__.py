"""Application factory de SIVEC.

Construye y configura la aplicación Flask siguiendo el patrón "application
factory": las extensiones se inicializan aquí y los blueprints se registran
bajo el prefijo /api. Esto facilita las pruebas y mantiene el arranque limpio.
"""

from dotenv import load_dotenv

# Cargamos las variables de .env ANTES de importar la configuración, porque
# app.config lee os.getenv(...) en el momento de importarse. Si cargáramos el
# .env más tarde, las clases de configuración ya habrían leído valores vacíos.
load_dotenv()

from flask import Flask

from app.config import obtener_configuracion
from app.extensions import db, migrate, jwt, cors
from app.utils.errores import (
    registrar_manejadores_errores, registrar_manejadores_jwt,
)


def create_app(nombre_entorno: str | None = None) -> Flask:
    """Crea y configura una instancia de la aplicación Flask.

    Args:
        nombre_entorno: "development", "testing" o "production".
            Si es None, se toma de la variable FLASK_ENV.
    """
    app = Flask(__name__)

    # --- Configuración ---
    configuracion = obtener_configuracion(nombre_entorno)
    app.config.from_object(configuracion)

    # --- Extensiones ---
    _inicializar_extensiones(app)

    # --- Modelos ---
    # Importamos los modelos para que queden registrados en el metadata de
    # SQLAlchemy y Flask-Migrate pueda detectarlos.
    with app.app_context():
        from app import models  # noqa: F401

    # --- Manejo uniforme de errores ---
    registrar_manejadores_errores(app)

    # --- Blueprints (rutas) ---
    _registrar_blueprints(app)

    # --- Comandos CLI (flask seed, etc.) ---
    _registrar_comandos(app)

    return app


def _inicializar_extensiones(app: Flask) -> None:
    """Asocia las extensiones a la aplicación."""
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    # Hacemos que los errores de JWT usen el formato uniforme del proyecto.
    registrar_manejadores_jwt(jwt)
    # CORS: solo permitimos los orígenes configurados, sobre las rutas /api/*
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config.get("CORS_ORIGENES", [])}},
        supports_credentials=True,
    )


def _registrar_blueprints(app: Flask) -> None:
    """Registra todos los blueprints bajo el prefijo /api."""
    from app.routes.salud import bp_salud
    from app.routes.auth import bp_auth
    from app.routes.usuarios import bp_usuarios
    from app.routes.peliculas import bp_peliculas
    from app.routes.salas import bp_salas
    from app.routes.funciones import bp_funciones

    app.register_blueprint(bp_salud, url_prefix="/api")
    app.register_blueprint(bp_auth, url_prefix="/api")
    app.register_blueprint(bp_usuarios, url_prefix="/api")
    app.register_blueprint(bp_peliculas, url_prefix="/api")
    app.register_blueprint(bp_salas, url_prefix="/api")
    app.register_blueprint(bp_funciones, url_prefix="/api")
    # En fases siguientes se registrarán aquí los demás blueprints
    # (asientos, reservas, compras, entradas, validaciones, reportes, etc.).


def _registrar_comandos(app: Flask) -> None:
    """Registra los comandos CLI personalizados de la aplicación."""

    @app.cli.command("seed")
    def seed():
        """Carga datos de prueba de forma idempotente (flask seed)."""
        from scripts.seed import ejecutar_seed
        ejecutar_seed()
