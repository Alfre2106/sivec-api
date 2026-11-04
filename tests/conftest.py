"""Configuración global de pytest para SIVEC.

Principios:
- Las pruebas usan SIEMPRE la base de pruebas (TEST_DATABASE_URL, p. ej.
  sivec_test), nunca la de desarrollo. Si falta, se crea automáticamente a
  partir de DATABASE_URL cambiando solo el nombre de la base.
- PostgreSQL real (no SQLite): la concurrencia depende de SELECT ... FOR UPDATE.
- El esquema se construye con las migraciones reales (así también se prueban).
- Antes de cada prueba se vacían todas las tablas (los hilos de las pruebas de
  concurrencia necesitan commits reales, por eso no se usa rollback).
- Configuración "testing": el scheduler NO se inicia.
"""

import os
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parent.parent
CLAVE_DEMO = "123456"
ROLES = ("administrador", "taquillero", "cliente")


# --- 1. Resolver la base de pruebas ANTES de importar la aplicación -------
# (app.config lee las variables de entorno en el momento de importarse).

def _preparar_entorno_de_pruebas() -> None:
    from sqlalchemy.engine import make_url

    valores = {**dotenv_values(RAIZ / ".env"), **os.environ}
    uri_trabajo = valores.get("DATABASE_URL")
    uri_pruebas = valores.get("TEST_DATABASE_URL")

    if not uri_pruebas and uri_trabajo:
        # Respaldo cómodo: misma conexión, base "<nombre>_test".
        url = make_url(uri_trabajo)
        uri_pruebas = url.set(database=f"{url.database}_test").render_as_string(
            hide_password=False)
    if not uri_pruebas:
        pytest.exit("Falta TEST_DATABASE_URL (o DATABASE_URL) en el .env.",
                    returncode=2)

    if uri_trabajo:
        os.environ.setdefault("DATABASE_URL", uri_trabajo)
    os.environ["TEST_DATABASE_URL"] = uri_pruebas


def _crear_base_si_no_existe(uri: str) -> None:
    """Crea la base de pruebas si todavía no existe."""
    import psycopg2
    from sqlalchemy.engine import make_url

    url = make_url(uri)
    try:
        conexion = psycopg2.connect(
            host=url.host, port=url.port, user=url.username,
            password=url.password, dbname="postgres")
    except psycopg2.Error as error:
        pytest.exit(f"No se pudo conectar a PostgreSQL: {error}", returncode=2)
    conexion.autocommit = True
    with conexion.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                       (url.database,))
        if cursor.fetchone() is None:
            cursor.execute(f'CREATE DATABASE "{url.database}"')
    conexion.close()


_preparar_entorno_de_pruebas()

# Importaciones de la aplicación: deben ir DESPUÉS de preparar el entorno.
from flask_jwt_extended import create_access_token  # noqa: E402
from flask_migrate import upgrade  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import create_app  # noqa: E402
from app.config import validar_uri_pruebas  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Cliente, Pelicula, Sala, Usuario  # noqa: E402
from app.models.enums import RolUsuario  # noqa: E402
from app.services.funciones_service import (  # noqa: E402
    _generar_asientos, crear_funcion,
)
from app.utils.seguridad import hashear_password  # noqa: E402
from app.utils.tiempo import ahora_utc  # noqa: E402


# --- 2. Aplicación y esquema (una vez por sesión) -------------------------

@pytest.fixture(scope="session")
def app():
    """Aplicación en modo "testing" con el esquema creado por las migraciones."""
    validar_uri_pruebas(os.environ["TEST_DATABASE_URL"])
    _crear_base_si_no_existe(os.environ["TEST_DATABASE_URL"])

    aplicacion = create_app("testing")
    assert aplicacion.config["TESTING"] is True

    with aplicacion.app_context():
        # Solo se llega aquí con la base de pruebas validada: se reconstruye.
        db.session.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        db.session.execute(text("CREATE SCHEMA public"))
        db.session.commit()
        upgrade(directory=str(RAIZ / "migrations"))
    return aplicacion


@pytest.fixture(autouse=True)
def bd_limpia(app):
    """Vacía todas las tablas antes de cada prueba (ids reiniciados)."""
    tablas = ", ".join(t.name for t in db.metadata.sorted_tables)
    with app.app_context():
        db.session.execute(
            text(f"TRUNCATE TABLE {tablas} RESTART IDENTITY CASCADE"))
        db.session.commit()
    yield


@pytest.fixture
def http(app):
    """Cliente HTTP de Flask."""
    return app.test_client()


# --- 3. Usuarios y tokens -------------------------------------------------

@pytest.fixture(scope="session")
def hash_demo():
    """Hash bcrypt de la clave de prueba, calculado una sola vez (es lento)."""
    return hashear_password(CLAVE_DEMO)


@pytest.fixture
def usuarios(app, hash_demo):
    """Un usuario por rol + un segundo cliente (para probar aislamiento)."""
    datos = [
        ("admin", "Admin Prueba", "admin@prueba.com", RolUsuario.ADMINISTRADOR, False),
        ("taquillero", "Taquillero Prueba", "taquillero@prueba.com", RolUsuario.TAQUILLERO, False),
        ("cliente", "Cliente Prueba", "cliente@prueba.com", RolUsuario.CLIENTE, True),
        ("otro_cliente", "Otro Cliente", "otro@prueba.com", RolUsuario.CLIENTE, True),
    ]
    resultado = {}
    with app.app_context():
        for clave, nombre, correo, rol, con_ficha in datos:
            usuario = Usuario(nombre=nombre, correo=correo,
                              password_hash=hash_demo, rol=rol, activo=True)
            db.session.add(usuario)
            db.session.flush()
            cliente_id = None
            if con_ficha:
                ficha = Cliente(usuario_id=usuario.id, nombre=nombre)
                db.session.add(ficha)
                db.session.flush()
                cliente_id = ficha.id
            resultado[clave] = SimpleNamespace(
                id=usuario.id, correo=correo, rol=rol.value,
                cliente_id=cliente_id)
        db.session.commit()
    return SimpleNamespace(**resultado)


@pytest.fixture
def auth(app, usuarios):
    """Cabeceras Authorization listas para usar, una por usuario."""
    def cabecera(usuario):
        with app.app_context():
            token = create_access_token(
                identity=str(usuario.id),
                additional_claims={"rol": usuario.rol})
        return {"Authorization": f"Bearer {token}"}

    return SimpleNamespace(
        admin=cabecera(usuarios.admin),
        taquillero=cabecera(usuarios.taquillero),
        cliente=cabecera(usuarios.cliente),
        otro_cliente=cabecera(usuarios.otro_cliente),
    )


# --- 4. Escenarios (película + sala + función con asientos) ---------------

@pytest.fixture
def crear_escenario(app, usuarios):
    """Fábrica de escenarios. Cada llamada crea su película y su sala.

    Args (de la fábrica):
        minutos: minutos desde ahora hasta el inicio (negativo = ya iniciada).
        filas, por_fila: distribución de la sala.
        precio: precio por entrada (COP).
        duracion_min: duración de la película.
    """
    contador = {"n": 0}

    def _crear(minutos=24 * 60, filas=3, por_fila=4, precio=20000,
               duracion_min=100):
        from app.models import Funcion
        from app.models.asiento_funcion import AsientoFuncion

        contador["n"] += 1
        n = contador["n"]
        with app.app_context():
            pelicula = Pelicula(titulo=f"Película {n}",
                                duracion_min=duracion_min, activa=True)
            sala = Sala(nombre=f"Sala {n}", filas=filas,
                        asientos_por_fila=por_fila, capacidad=filas * por_fila)
            db.session.add_all([pelicula, sala])
            db.session.flush()

            inicio = ahora_utc() + timedelta(minutes=minutos)
            if minutos > 0:
                # Camino real: valida y genera los asientos (CA-01).
                funcion = crear_funcion(
                    {"pelicula_id": pelicula.id, "sala_id": sala.id,
                     "inicio": inicio.isoformat(), "precio": precio},
                    admin_id=usuarios.admin.id)
            else:
                # Función ya iniciada: el servicio no lo permite, se arma a mano.
                funcion = Funcion(pelicula_id=pelicula.id, sala_id=sala.id,
                                  inicio=inicio, precio=precio)
                db.session.add(funcion)
                db.session.flush()
                _generar_asientos(funcion, sala)
                db.session.commit()

            asientos = [a.id for a in AsientoFuncion.query
                        .filter_by(funcion_id=funcion.id)
                        .order_by(AsientoFuncion.fila, AsientoFuncion.numero)]
            return SimpleNamespace(
                funcion_id=funcion.id, pelicula_id=pelicula.id,
                sala_id=sala.id, asientos=asientos, precio=precio,
                capacidad=filas * por_fila)

    return _crear
