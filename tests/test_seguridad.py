"""Autenticación, gestión de usuarios y seguridad (RNF-09, RNF-10)."""

import json
from datetime import timedelta

import pytest
from flask_jwt_extended import create_access_token, decode_token

from app.config import validar_secretos_produccion, validar_uri_pruebas
from tests.utilidades import filas_sql, valor_sql


def login(http, correo, password="123456"):
    return http.post("/api/auth/login", json={"correo": correo, "password": password})


def test_login_de_cada_rol_devuelve_token_y_usuario(http, usuarios):
    """El login devuelve {token, usuario: {id, nombre, correo, rol, cliente_id}}."""
    for u in (usuarios.admin, usuarios.taquillero, usuarios.cliente):
        respuesta = login(http, u.correo)
        assert respuesta.status_code == 200
        cuerpo = respuesta.get_json()
        assert cuerpo["token"]
        assert cuerpo["usuario"]["rol"] == u.rol
        assert cuerpo["usuario"]["cliente_id"] == u.cliente_id
        assert {"id", "nombre", "correo", "rol", "cliente_id"} <= set(cuerpo["usuario"])


def test_login_fallido_usa_el_mismo_mensaje_generico(http, usuarios):
    """Correo inexistente y clave incorrecta son indistinguibles (401)."""
    inexistente = login(http, "nadie@prueba.com")
    mala_clave = login(http, usuarios.admin.correo, "incorrecta")

    for r in (inexistente, mala_clave):
        assert r.status_code == 401
        assert r.get_json() == {"error": {
            "codigo": "CREDENCIALES_INVALIDAS",
            "mensaje": "Correo o contraseña incorrectos."}}
    assert login(http, usuarios.admin.correo, "").status_code == 422


def test_usuario_inactivo_no_puede_iniciar_sesion(http, auth, usuarios):
    """Desactivar un usuario le impide entrar (se conserva su historial)."""
    creado = http.post("/api/usuarios", headers=auth.admin, json={
        "nombre": "Taq Dos", "correo": "taq2@prueba.com", "password": "123456",
        "rol": "taquillero"})
    assert creado.status_code == 201
    assert login(http, "taq2@prueba.com").status_code == 200

    assert http.delete(f"/api/usuarios/{creado.get_json()['usuario']['id']}",
                       headers=auth.admin).status_code == 200

    assert login(http, "taq2@prueba.com").status_code == 401


def test_token_incluye_rol_y_expira_segun_configuracion(app, http, usuarios):
    """El JWT lleva el rol y vence según JWT_EXPIRACION_MINUTOS."""
    token = login(http, usuarios.taquillero.correo).get_json()["token"]
    with app.app_context():
        claims = decode_token(token)
    assert claims["rol"] == "taquillero"
    assert claims["sub"] == str(usuarios.taquillero.id)
    esperado = app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds()
    assert claims["exp"] - claims["iat"] == pytest.approx(esperado, abs=2)


def test_errores_jwt_usan_el_formato_uniforme(app, http, usuarios):
    """Token ausente, inválido o vencido: 401 con {"error": {"codigo", "mensaje"}}."""
    ausente = http.get("/api/auth/yo")
    invalido = http.get("/api/auth/yo", headers={"Authorization": "Bearer abc.def.ghi"})
    with app.app_context():
        vencido_token = create_access_token(
            identity=str(usuarios.admin.id), additional_claims={"rol": "administrador"},
            expires_delta=timedelta(seconds=-5))
    vencido = http.get("/api/auth/yo", headers={"Authorization": f"Bearer {vencido_token}"})

    assert [r.status_code for r in (ausente, invalido, vencido)] == [401, 401, 401]
    assert ausente.get_json()["error"]["codigo"] == "TOKEN_AUSENTE"
    assert invalido.get_json()["error"]["codigo"] == "TOKEN_INVALIDO"
    assert vencido.get_json()["error"]["codigo"] == "TOKEN_VENCIDO"
    for r in (ausente, invalido, vencido):
        assert set(r.get_json()) == {"error"}
        assert set(r.get_json()["error"]) == {"codigo", "mensaje"}


def test_errores_http_estandar_tienen_el_mismo_formato(http):
    """Rutas inexistentes o métodos no permitidos también responden con el formato uniforme."""
    inexistente = http.get("/api/no-existe")
    assert inexistente.status_code == 404
    assert set(inexistente.get_json()["error"]) == {"codigo", "mensaje"}
    assert http.delete("/api/salud").status_code == 405


def test_password_hash_nunca_sale_en_una_respuesta(app, http, auth, usuarios):
    """Revisa las respuestas de auth y usuarios: ni `password_hash` ni la clave."""
    respuestas = [
        login(http, usuarios.admin.correo),
        http.post("/api/auth/registro", json={
            "nombre": "Z", "correo": "z@prueba.com", "password": "claveZ123"}),
        http.get("/api/auth/yo", headers=auth.admin),
        http.get("/api/usuarios", headers=auth.admin),
        http.get("/api/usuarios?rol=cliente", headers=auth.admin),
        http.post("/api/usuarios", headers=auth.admin, json={
            "nombre": "T", "correo": "t@prueba.com", "password": "claveT123",
            "rol": "taquillero"}),
        http.put(f"/api/usuarios/{usuarios.cliente.id}", headers=auth.admin,
                 json={"nombre": "Editado", "password": "claveNueva1"}),
    ]
    for r in respuestas:
        texto = r.get_data(as_text=True)
        assert r.status_code < 300, texto
        assert "password" not in texto.lower() and "$2b$" not in texto
        assert "claveZ123" not in texto and "claveNueva1" not in texto


def test_la_auditoria_no_guarda_contrasenas(app, http, auth, usuarios):
    """Registro, login (ok y fallido) y gestión de usuarios se auditan sin claves."""
    http.post("/api/auth/registro", json={
        "nombre": "Z", "correo": "z@prueba.com", "password": "claveSecreta9"})
    login(http, usuarios.admin.correo)
    login(http, usuarios.admin.correo, "claveMala777")
    http.post("/api/usuarios", headers=auth.admin, json={
        "nombre": "T", "correo": "t@prueba.com", "password": "claveTaq555", "rol": "taquillero"})
    http.put(f"/api/usuarios/{usuarios.cliente.id}", headers=auth.admin,
             json={"password": "claveEdit888"})

    acciones = {a for (a,) in filas_sql(app, "SELECT accion FROM auditoria")}
    assert {"registro", "login_exitoso", "login_fallido", "crear_usuario",
            "editar_usuario"} <= acciones
    volcado = json.dumps(filas_sql(app, "SELECT accion, detalle FROM auditoria"),
                         default=str)
    for secreto in ("claveSecreta9", "claveMala777", "claveTaq555", "claveEdit888", "123456"):
        assert secreto not in volcado


def test_crud_de_usuarios_solo_administrador(app, http, auth, usuarios):
    """Taquilleros y administradores solo los crea un administrador."""
    ruta = "/api/usuarios"
    nuevo = {"nombre": "Admin Dos", "correo": "admin2@prueba.com",
             "password": "123456", "rol": "administrador"}
    assert http.post(ruta, headers=auth.taquillero, json=nuevo).status_code == 403
    assert http.post(ruta, headers=auth.cliente, json=nuevo).status_code == 403
    creado = http.post(ruta, headers=auth.admin, json=nuevo)
    assert creado.status_code == 201 and creado.get_json()["usuario"]["rol"] == "administrador"

    # Por esta vía no se crean clientes ni se aceptan roles raros.
    cliente = http.post(ruta, headers=auth.admin, json={**nuevo, "correo": "c@prueba.com",
                                                        "rol": "cliente"})
    assert cliente.status_code == 422
    assert cliente.get_json()["error"]["codigo"] == "ROL_NO_PERMITIDO"
    assert http.post(ruta, headers=auth.admin, json={**nuevo, "correo": "d@prueba.com",
                                                     "rol": "dios"}).status_code == 422
    assert http.post(ruta, headers=auth.admin, json=nuevo).status_code == 409   # correo repetido

    filtrados = http.get(f"{ruta}?rol=taquillero", headers=auth.admin).get_json()["usuarios"]
    assert [u["rol"] for u in filtrados] == ["taquillero"]
    assert http.get(f"{ruta}?rol=otro", headers=auth.admin).status_code == 422
    editado = http.put(f"{ruta}/{usuarios.cliente.id}", headers=auth.admin,
                       json={"nombre": "Nombre Nuevo"})
    assert editado.get_json()["usuario"]["nombre"] == "Nombre Nuevo"
    assert http.put(f"{ruta}/99999", headers=auth.admin, json={}).status_code == 404


def test_restricciones_unique_como_segunda_defensa(app, usuarios, crear_escenario):
    """Las restricciones UNIQUE de la base impiden duplicados aunque falle la lógica."""
    from sqlalchemy.exc import IntegrityError
    from app.extensions import db
    from app.models import AsientoFuncion, Compra, Entrada
    from app.models.enums import EstadoPago

    esc = crear_escenario()
    with app.app_context():
        db.session.add(AsientoFuncion(funcion_id=esc.funcion_id, fila="A", numero=1))
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()

        compra = Compra(cliente_id=usuarios.cliente.cliente_id, usuario_id=usuarios.cliente.id,
                        funcion_id=esc.funcion_id, total=1, metodo_pago="tarjeta",
                        estado_pago=EstadoPago.APROBADO)
        db.session.add(compra)
        db.session.flush()
        for _ in range(2):
            db.session.add(Entrada(codigo="SIV-REPETIDO0001", compra_id=compra.id,
                                   funcion_id=esc.funcion_id, asiento_id=esc.asientos[0]))
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()
    assert valor_sql(app, "SELECT count(*) FROM entradas") == 0


def test_las_pruebas_no_pueden_apuntar_a_la_base_de_trabajo(monkeypatch):
    """Salvaguarda: TEST_DATABASE_URL debe existir, llevar 'test' y diferir de DATABASE_URL."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@localhost:5432/sivec")
    with pytest.raises(RuntimeError, match="Falta TEST_DATABASE_URL"):
        validar_uri_pruebas(None)
    with pytest.raises(RuntimeError, match="debe llevar 'test'"):
        validar_uri_pruebas("postgresql+psycopg2://u:p@localhost:5432/sivec")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://u:p@localhost:5432/sivec_test")
    with pytest.raises(RuntimeError, match="misma base"):
        validar_uri_pruebas("postgresql+psycopg2://u:p@localhost:5432/sivec_test")
    validar_uri_pruebas("postgresql+psycopg2://u:p@localhost:5432/otra_test")   # no lanza


def test_produccion_exige_claves_propias():
    """En producción no se aceptan las claves de desarrollo."""
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validar_secretos_produccion({"SECRET_KEY": "clave-insegura-solo-dev",
                                     "JWT_SECRET_KEY": "x" * 40})
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        validar_secretos_produccion({"SECRET_KEY": "y" * 40, "JWT_SECRET_KEY": None})
    validar_secretos_produccion({"SECRET_KEY": "y" * 40, "JWT_SECRET_KEY": "x" * 40})


def test_los_errores_de_sql_no_exponen_el_hash_de_la_contrasena(app, usuarios):
    """Un fallo al guardar un usuario no debe dejar el password_hash en el mensaje de error."""
    from sqlalchemy.exc import IntegrityError
    from app.extensions import db
    from app.models import Usuario
    from app.models.enums import RolUsuario

    hash_unico = "$2b$12$HASH.DE.PRUEBA.QUE.NO.DEBE.SALIR.EN.NINGUN.ERROR"
    with app.app_context():
        db.session.add(Usuario(nombre="Duplicado", correo=usuarios.admin.correo,
                               password_hash=hash_unico, rol=RolUsuario.CLIENTE))
        with pytest.raises(IntegrityError) as error:
            db.session.flush()
        db.session.rollback()

    texto = str(error.value)
    assert hash_unico not in texto
    assert "hidden" in texto            # SQLAlchemy avisa que ocultó los valores


def test_run_py_no_expone_el_depurador_en_todas_las_interfaces():
    """run.py escucha solo en 127.0.0.1 por defecto y el debug depende del entorno."""
    from pathlib import Path
    codigo = (Path(__file__).resolve().parent.parent / "run.py").read_text(encoding="utf-8")
    sin_comentarios = "\n".join(
        linea for linea in codigo.splitlines() if not linea.lstrip().startswith("#"))
    assert 'getenv("FLASK_HOST", "127.0.0.1")' in codigo
    assert "debug=True" not in sin_comentarios
    assert 'host="0.0.0.0"' not in sin_comentarios
