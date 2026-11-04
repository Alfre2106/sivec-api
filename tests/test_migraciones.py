"""Las migraciones deben describir exactamente el esquema que definen los modelos."""

from flask_migrate import check


def test_modelos_y_migraciones_estan_sincronizados(app):
    """Si alguien cambia un modelo y olvida crear la migración, esta prueba falla.

    `check` compara los modelos contra la base ya migrada (la fixture `app`
    construye la base de pruebas con `flask db upgrade`) y lanza un error si
    `flask db migrate` generaría cambios pendientes.
    """
    with app.app_context():
        check()
