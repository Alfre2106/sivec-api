"""Punto de entrada de la aplicación SIVEC.

Uso en desarrollo:
    python run.py
o bien, usando el CLI de Flask:
    flask --app run run

Variables opcionales del .env:
    FLASK_HOST  Dirección donde escucha (por defecto 127.0.0.1, solo este equipo).
                Usa 0.0.0.0 únicamente si otros equipos de la red deben acceder
                a la API; con 0.0.0.0 NO conviene tener el modo debug activo.
    FLASK_PORT  Puerto (por defecto 5000).
"""

import os

from app import create_app

# Instancia de la aplicación para el servidor y para el CLI de Flask.
app = create_app()


if __name__ == "__main__":
    # Seguridad: por defecto solo se escucha en este equipo. El modo debug
    # (depurador interactivo de Werkzeug) lo decide la configuración del entorno:
    # activo en "development", apagado en "production".
    app.run(
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=bool(app.config.get("DEBUG")),
    )
