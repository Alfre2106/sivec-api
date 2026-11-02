"""Instancias de las extensiones de Flask.

Se crean aquí sin asociarlas todavía a una app concreta. La asociación
(`init_app`) se hace en el application factory (`create_app`). Esto evita
importaciones circulares y permite usar las mismas instancias en toda la app.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS

# ORM y acceso a la base de datos
db = SQLAlchemy()

# Migraciones de esquema (Alembic)
migrate = Migrate()

# Gestión de tokens JWT
jwt = JWTManager()

# Control de CORS para el frontend
cors = CORS()
