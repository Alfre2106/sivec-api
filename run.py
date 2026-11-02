"""Punto de entrada de la aplicación SIVEC.

Uso en desarrollo:
    python run.py
o bien, usando el CLI de Flask (ver variable FLASK_APP):
    flask run
"""

from app import create_app

# Instancia de la aplicación para el servidor y para el CLI de Flask.
app = create_app()


if __name__ == "__main__":
    # El host 0.0.0.0 permite acceder desde otros equipos de la red local.
    app.run(host="0.0.0.0", port=5000, debug=True)
