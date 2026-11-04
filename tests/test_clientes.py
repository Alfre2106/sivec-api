"""Registro de clientes y aislamiento de sus datos (CA-13, RN-12)."""

from tests.utilidades import codigos_de, comprar, filas_sql, valor_sql


def _registrar(http, correo="nuevo@prueba.com", **extra):
    cuerpo = {"nombre": "Ana Pérez", "correo": correo, "password": "secreto1",
              "documento": "1001", "contacto": "3001234567", **extra}
    return http.post("/api/auth/registro", json=cuerpo)


def test_ca13_cliente_se_registra_y_queda_con_su_ficha(app, http):
    """CA-13: el registro crea usuario 'cliente' + ficha en `clientes` y devuelve token."""
    respuesta = _registrar(http)

    assert respuesta.status_code == 201
    cuerpo = respuesta.get_json()
    assert cuerpo["token"]
    usuario = cuerpo["usuario"]
    assert usuario["rol"] == "cliente"
    assert usuario["cliente_id"] is not None
    assert "password" not in usuario and "password_hash" not in usuario
    assert filas_sql(app, "SELECT nombre, documento, contacto, usuario_id FROM clientes") == [
        ("Ana Pérez", "1001", "3001234567", usuario["id"])]
    # La contraseña se guarda con hash bcrypt, nunca en texto plano.
    guardado = valor_sql(app, "SELECT password_hash FROM usuarios WHERE id = :i", i=usuario["id"])
    assert guardado.startswith("$2") and "secreto1" not in guardado
    # El token recién emitido sirve para /auth/yo y el login posterior funciona.
    yo = http.get("/api/auth/yo", headers={"Authorization": f"Bearer {cuerpo['token']}"})
    assert yo.get_json()["usuario"]["correo"] == "nuevo@prueba.com"
    login = http.post("/api/auth/login", json={"correo": "nuevo@prueba.com",
                                               "password": "secreto1"})
    assert login.status_code == 200


def test_ca13_el_registro_publico_solo_crea_clientes(app, http):
    """El registro público ignora cualquier intento de elegir rol."""
    respuesta = _registrar(http, rol="administrador", activo=False)
    assert respuesta.status_code == 201
    assert respuesta.get_json()["usuario"]["rol"] == "cliente"
    assert valor_sql(app, "SELECT count(*) FROM usuarios WHERE rol <> 'cliente'") == 0


def test_ca13_validaciones_del_registro(app, http):
    """Correo normalizado y único, formato válido, contraseña de 6+ caracteres."""
    assert _registrar(http, correo="  MAYUS@Prueba.COM ").status_code == 201
    assert valor_sql(app, "SELECT correo FROM usuarios") == "mayus@prueba.com"

    repetido = _registrar(http, correo="mayus@prueba.com")
    assert repetido.status_code == 409
    assert repetido.get_json()["error"]["codigo"] == "CORREO_YA_REGISTRADO"
    assert _registrar(http, correo="no-es-correo").status_code == 422
    corta = http.post("/api/auth/registro", json={
        "nombre": "X", "correo": "x@prueba.com", "password": "123"})
    assert corta.status_code == 422
    assert corta.get_json()["error"]["codigo"] == "PASSWORD_CORTA"
    assert http.post("/api/auth/registro", json={"correo": "y@prueba.com"}).status_code == 422


def test_ca13_cliente_solo_ve_sus_propias_compras_y_entradas(
        app, http, auth, crear_escenario):
    """CA-13 / RN-12: cada cliente ve únicamente lo suyo."""
    esc = crear_escenario()
    mia = comprar(http, auth.cliente, esc.funcion_id, esc.asientos[:2])
    ajena = comprar(http, auth.otro_cliente, esc.funcion_id, esc.asientos[2:3])
    # Una compra rechazada tampoco aparece en "mis compras".
    comprar(http, auth.cliente, esc.funcion_id, [esc.asientos[4]], resultado="rechazado")

    mias = http.get("/api/mis-compras", headers=auth.cliente).get_json()["compras"]
    assert [c["id"] for c in mias] == [mia.get_json()["compra"]["id"]]
    assert sorted(e["codigo"] for e in mias[0]["entradas"]) == sorted(codigos_de(mia))
    assert {"codigo", "estado", "fila", "numero"} <= set(mias[0]["entradas"][0])

    de_otro = http.get("/api/mis-compras", headers=auth.otro_cliente).get_json()["compras"]
    assert [c["id"] for c in de_otro] == [ajena.get_json()["compra"]["id"]]

    # La entrada de otro cliente: detalle y QR prohibidos (403).
    entrada_ajena = ajena.get_json()["entradas"][0]["id"]
    for ruta in (f"/api/entradas/{entrada_ajena}", f"/api/entradas/{entrada_ajena}/qr"):
        prohibido = http.get(ruta, headers=auth.cliente)
        assert prohibido.status_code == 403
        assert prohibido.get_json()["error"]["codigo"] == "ENTRADA_AJENA"
    # Taquillero y administrador sí pueden; el dueño también.
    for cabecera in (auth.taquillero, auth.admin, auth.otro_cliente):
        assert http.get(f"/api/entradas/{entrada_ajena}", headers=cabecera).status_code == 200
    assert http.get("/api/entradas/99999", headers=auth.admin).status_code == 404


def test_ca13_qr_es_una_imagen_png(http, auth, crear_escenario):
    """El QR de la entrada se entrega como imagen PNG."""
    esc = crear_escenario()
    entrada = comprar(http, auth.cliente, esc.funcion_id,
                      esc.asientos[:1]).get_json()["entradas"][0]["id"]

    qr = http.get(f"/api/entradas/{entrada}/qr", headers=auth.cliente)

    assert qr.status_code == 200
    assert qr.mimetype == "image/png"
    assert qr.data.startswith(b"\x89PNG\r\n\x1a\n")


def test_ca13_ventas_taquillero_y_administrador(http, auth, crear_escenario):
    """El taquillero ve solo sus ventas; el administrador, todas (con filtros)."""
    esc = crear_escenario()
    comprar(http, auth.taquillero, esc.funcion_id, [esc.asientos[0]], metodo_pago="efectivo",
            cliente={"nombre": "Walk In", "documento": "9", "contacto": "300"})
    comprar(http, auth.cliente, esc.funcion_id, [esc.asientos[1]])

    del_taquillero = http.get("/api/ventas", headers=auth.taquillero).get_json()["ventas"]
    assert len(del_taquillero) == 1
    assert del_taquillero[0]["cliente"]["nombre"] == "Walk In"
    assert del_taquillero[0]["metodo_pago"] == "efectivo"
    assert len(http.get("/api/ventas", headers=auth.admin).get_json()["ventas"]) == 2
    assert len(http.get("/api/ventas?desde=2020-01-01&hasta=2020-12-31",
                        headers=auth.admin).get_json()["ventas"]) == 0
    assert http.get("/api/ventas", headers=auth.cliente).status_code == 403
    assert http.get("/api/mis-compras", headers=auth.taquillero).status_code == 403
