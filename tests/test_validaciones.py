"""Validación de entradas en la puerta (CA-08, CA-09)."""

import pytest

from tests.utilidades import (
    codigos_de, comprar, ejecutar_sql, filas_sql, valor_sql, validar,
)


@pytest.fixture
def entradas_proximas(http, auth, crear_escenario):
    """Función que empieza en 30 min (dentro de la ventana de validación)."""
    esc = crear_escenario(minutos=30)
    compra = comprar(http, auth.cliente, esc.funcion_id, esc.asientos[:2])
    assert compra.status_code == 201
    esc.codigos = codigos_de(compra)
    return esc


def test_ca08_entrada_valida_se_marca_como_usada(app, http, auth, usuarios, entradas_proximas):
    """CA-08: una entrada vigente da acceso, se marca 'usada' y se audita."""
    esc = entradas_proximas
    codigo = esc.codigos[0]

    # Se normaliza: minúsculas y espacios.
    respuesta = validar(http, auth.taquillero, f"  {codigo.lower()}  ")

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_json()
    assert cuerpo["resultado"] == "valida"
    assert cuerpo["acceso_permitido"] is True
    assert cuerpo["entrada"]["codigo"] == codigo
    assert cuerpo["entrada"]["estado"] == "usada"
    assert cuerpo["funcion"]["id"] == esc.funcion_id
    assert cuerpo["primer_uso"] is None
    assert cuerpo["validacion_id"] > 0
    assert valor_sql(app, "SELECT estado FROM entradas WHERE codigo = :c", c=codigo) == "usada"
    assert valor_sql(app, "SELECT usada_en IS NOT NULL FROM entradas WHERE codigo = :c",
                     c=codigo) is True
    assert filas_sql(app, "SELECT usuario_id, entidad FROM auditoria "
                          "WHERE accion = 'validar_entrada'") == [
        (usuarios.taquillero.id, "entradas")]


def test_ca08_entrada_ya_usada_informa_el_primer_uso(app, http, auth, entradas_proximas):
    """CA-08 / RN-07: la segunda lectura da 'ya_usada' con fecha y taquillero."""
    codigo = entradas_proximas.codigos[0]
    assert validar(http, auth.taquillero, codigo).get_json()["resultado"] == "valida"

    segunda = validar(http, auth.admin, codigo)

    assert segunda.status_code == 200
    cuerpo = segunda.get_json()
    assert cuerpo["resultado"] == "ya_usada"
    assert cuerpo["acceso_permitido"] is False
    assert cuerpo["primer_uso"]["taquillero"] == "Taquillero Prueba"
    assert cuerpo["primer_uso"]["fecha"]


def test_ca09_codigo_inexistente_es_invalido_y_queda_registrado(app, http, auth):
    """CA-09: un código que no existe da 'invalida' y se guarda sin entrada."""
    respuesta = validar(http, auth.taquillero, "SIV-NOEXISTE0000")

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_json()
    assert cuerpo["resultado"] == "invalida"
    assert cuerpo["acceso_permitido"] is False
    assert cuerpo["entrada"] is None and cuerpo["funcion"] is None
    assert cuerpo["mensaje"] == "La entrada no es válida."
    assert filas_sql(app, "SELECT entrada_id, codigo_leido, resultado "
                          "FROM validaciones") == [(None, "SIV-NOEXISTE0000", "invalida")]


def test_ca09_entrada_de_otra_funcion(app, http, auth, crear_escenario, entradas_proximas):
    """CA-09: si el taquillero indica otra función, se informa a cuál pertenece."""
    otra = crear_escenario(minutos=40)
    codigo = entradas_proximas.codigos[0]

    respuesta = validar(http, auth.taquillero, codigo, funcion_id=otra.funcion_id)

    cuerpo = respuesta.get_json()
    assert respuesta.status_code == 200
    assert cuerpo["resultado"] == "otra_funcion"
    assert cuerpo["acceso_permitido"] is False
    assert cuerpo["funcion"]["id"] == entradas_proximas.funcion_id
    assert {"pelicula", "sala", "inicio"} <= set(cuerpo["funcion"])
    # La entrada NO se consumió.
    assert valor_sql(app, "SELECT estado FROM entradas WHERE codigo = :c", c=codigo) == "activa"
    # Con la función correcta sí entra.
    ok = validar(http, auth.taquillero, codigo, funcion_id=entradas_proximas.funcion_id)
    assert ok.get_json()["resultado"] == "valida"


def test_ca09_fuera_de_la_ventana_horaria(app, http, auth, crear_escenario):
    """CA-09: antes de la apertura (120 min) o después del fin => 'otra_funcion'."""
    lejana = crear_escenario(minutos=24 * 60)
    codigo_lejano = codigos_de(comprar(http, auth.cliente, lejana.funcion_id,
                                       lejana.asientos[:1]))[0]
    antes = validar(http, auth.taquillero, codigo_lejano).get_json()
    assert antes["resultado"] == "otra_funcion"
    assert antes["mensaje"].startswith("La entrada corresponde a la función de")

    terminada = crear_escenario(minutos=30)
    codigo_viejo = codigos_de(comprar(http, auth.cliente, terminada.funcion_id,
                                      terminada.asientos[:1]))[0]
    ejecutar_sql(app, "UPDATE funciones SET inicio = now() - interval '5 hours' "
                      "WHERE id = :f", f=terminada.funcion_id)
    despues = validar(http, auth.taquillero, codigo_viejo).get_json()
    assert despues["resultado"] == "otra_funcion"
    assert valor_sql(app, "SELECT estado FROM entradas WHERE codigo = :c",
                     c=codigo_viejo) == "activa"


def test_ca09_entrada_anulada_por_funcion_cancelada(http, auth, entradas_proximas):
    """CA-09 / RN-10: una entrada anulada no da acceso."""
    esc = entradas_proximas
    cancelar = http.post(f"/api/funciones/{esc.funcion_id}/cancelar",
                         headers=auth.admin, json={"motivo": "prueba"})
    assert cancelar.status_code == 200

    respuesta = validar(http, auth.taquillero, esc.codigos[0])

    assert respuesta.get_json()["resultado"] == "anulada"
    assert respuesta.get_json()["acceso_permitido"] is False


def test_ca08_roles_y_cuerpo_invalido(http, auth, entradas_proximas):
    """Solo taquillero y administrador validan; el cuerpo se valida (422)."""
    codigo = entradas_proximas.codigos[0]
    assert validar(http, auth.cliente, codigo).status_code == 403
    assert http.post("/api/validaciones", json={"codigo": codigo}).status_code == 401
    assert http.post("/api/validaciones", headers=auth.taquillero, json={}).status_code == 422
    assert http.post("/api/validaciones", headers=auth.taquillero,
                     json={"codigo": codigo, "funcion_id": "x"}).status_code == 422


def test_ca09_todos_los_intentos_quedan_registrados_y_el_historial_filtra(
        app, http, auth, usuarios, entradas_proximas):
    """CA-09: se guardan TODOS los intentos; el taquillero ve solo los suyos."""
    codigo = entradas_proximas.codigos[0]
    validar(http, auth.taquillero, "SIV-INEXISTENTE1")
    validar(http, auth.taquillero, codigo)
    validar(http, auth.taquillero, codigo)
    validar(http, auth.admin, "SIV-INEXISTENTE2")

    assert valor_sql(app, "SELECT count(*) FROM validaciones") == 4

    propias = http.get("/api/validaciones", headers=auth.taquillero).get_json()["validaciones"]
    assert len(propias) == 3
    todas = http.get("/api/validaciones", headers=auth.admin).get_json()["validaciones"]
    assert len(todas) == 4
    filtradas = http.get("/api/validaciones?resultado=ya_usada&limite=5",
                         headers=auth.admin).get_json()["validaciones"]
    assert [v["resultado"] for v in filtradas] == ["ya_usada"]
    assert http.get("/api/validaciones?resultado=otro", headers=auth.admin).status_code == 422
    assert http.get("/api/validaciones", headers=auth.cliente).status_code == 403
