"""Cancelación de funciones con anulación de entradas (CA-15)."""

from tests.utilidades import (
    comprar, estado_asiento, filas_sql, reservar, valor_sql, validar,
)


def _preparar(http, auth, crear_escenario):
    """Función en 30 min con: compra de 2 (una entrada ya usada), compra de 1
    de otro cliente y una reserva activa del taquillero."""
    esc = crear_escenario(minutos=30, precio=20000)
    compra_1 = comprar(http, auth.cliente, esc.funcion_id, esc.asientos[:2])
    compra_2 = comprar(http, auth.otro_cliente, esc.funcion_id, [esc.asientos[2]])
    esc.usada = compra_1.get_json()["entradas"][0]["codigo"]
    assert validar(http, auth.taquillero, esc.usada).get_json()["resultado"] == "valida"
    assert reservar(http, auth.taquillero, esc.funcion_id,
                    [esc.asientos[5]]).status_code == 201
    esc.compra_1 = compra_1.get_json()["compra"]["id"]
    esc.compra_2 = compra_2.get_json()["compra"]["id"]
    return esc


def test_ca15_cancelar_funcion_anula_entradas_y_devuelve_afectados(
        app, http, auth, crear_escenario):
    """CA-15 / RN-10: anula las entradas ACTIVAS, libera reservas y lista los afectados."""
    esc = _preparar(http, auth, crear_escenario)

    respuesta = http.post(f"/api/funciones/{esc.funcion_id}/cancelar",
                          headers=auth.admin, json={"motivo": "Falla del proyector"})

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_json()
    assert cuerpo["funcion"]["estado"] == "cancelada"
    assert cuerpo["entradas_anuladas"] == 2          # la usada no se toca
    assert cuerpo["total_a_reembolsar"] == 60000
    afectados = {c["compra_id"]: c for c in cuerpo["compras_afectadas"]}
    assert set(afectados) == {esc.compra_1, esc.compra_2}
    primera = afectados[esc.compra_1]
    assert primera["numero"] == f"C-{esc.compra_1:06d}"
    assert primera["cantidad_entradas"] == 2 and primera["total"] == 40000
    assert primera["metodo_pago"] == "tarjeta"
    assert set(primera["cliente"]) == {"nombre", "documento", "contacto"}
    assert primera["cliente"]["nombre"] == "Cliente Prueba"

    estados = dict(filas_sql(app, "SELECT codigo, estado FROM entradas"))
    assert estados[esc.usada] == "usada"
    assert sorted(estados.values()) == ["anulada", "anulada", "usada"]
    assert filas_sql(app, "SELECT DISTINCT estado FROM reservas "
                          "WHERE estado <> 'convertida'") == [("cancelada",)]
    assert estado_asiento(app, esc.asientos[5]) == "disponible"
    assert valor_sql(app, "SELECT detalle->>'motivo' FROM auditoria "
                          "WHERE accion = 'cancelar_funcion'") == "Falla del proyector"


def test_ca15_afectados_consultable_despues_de_cancelar(http, auth, crear_escenario):
    """CA-15: GET /funciones/:id/afectados repite la lista (solo administrador)."""
    esc = _preparar(http, auth, crear_escenario)
    http.post(f"/api/funciones/{esc.funcion_id}/cancelar", headers=auth.admin,
              json={"motivo": "prueba"})

    lista = http.get(f"/api/funciones/{esc.funcion_id}/afectados", headers=auth.admin)

    assert lista.status_code == 200
    assert len(lista.get_json()["compras_afectadas"]) == 2
    assert http.get(f"/api/funciones/{esc.funcion_id}/afectados",
                    headers=auth.taquillero).status_code == 403


def test_ca15_mis_compras_muestra_funcion_cancelada_y_entradas_anuladas(
        http, auth, crear_escenario):
    """CA-15: el cliente ve la función 'cancelada' y sus entradas 'anulada'/'usada'."""
    esc = _preparar(http, auth, crear_escenario)
    http.post(f"/api/funciones/{esc.funcion_id}/cancelar", headers=auth.admin,
              json={"motivo": "prueba"})

    compras = http.get("/api/mis-compras", headers=auth.cliente).get_json()["compras"]

    assert len(compras) == 1
    assert compras[0]["funcion"]["estado"] == "cancelada"
    assert sorted(e["estado"] for e in compras[0]["entradas"]) == ["anulada", "usada"]


def test_ca15_reglas_de_la_cancelacion(app, http, auth, crear_escenario):
    """Motivo obligatorio, solo administrador, no se cancela dos veces ni lo finalizado."""
    esc = crear_escenario(minutos=24 * 60)
    ruta = f"/api/funciones/{esc.funcion_id}/cancelar"

    assert http.post(ruta, headers=auth.admin, json={}).status_code == 422
    assert http.post(ruta, headers=auth.taquillero, json={"motivo": "x"}).status_code == 403
    assert http.post(ruta, headers=auth.cliente, json={"motivo": "x"}).status_code == 403
    assert http.post("/api/funciones/99999/cancelar", headers=auth.admin,
                     json={"motivo": "x"}).status_code == 404

    assert http.post(ruta, headers=auth.admin, json={"motivo": "x"}).status_code == 200
    de_nuevo = http.post(ruta, headers=auth.admin, json={"motivo": "x"})
    assert de_nuevo.status_code == 409
    assert de_nuevo.get_json()["error"]["codigo"] == "FUNCION_YA_CANCELADA"

    # Ya no se puede reservar ni comprar (RN-08).
    assert reservar(http, auth.cliente, esc.funcion_id,
                    [esc.asientos[0]]).status_code == 409
    assert comprar(http, auth.cliente, esc.funcion_id,
                   [esc.asientos[0]]).status_code == 409

    terminada = crear_escenario(minutos=-300)
    fin = http.post(f"/api/funciones/{terminada.funcion_id}/cancelar",
                    headers=auth.admin, json={"motivo": "x"})
    assert fin.status_code == 409
    assert fin.get_json()["error"]["codigo"] == "FUNCION_FINALIZADA"


def test_ca15_funcion_con_ventas_no_se_elimina_ni_cambia_de_sala(http, auth, crear_escenario):
    """RF-01: con ventas solo se puede cancelar, no eliminar; y solo cambia el precio."""
    esc = crear_escenario(minutos=24 * 60)
    comprar(http, auth.cliente, esc.funcion_id, esc.asientos[:1])

    borrar = http.delete(f"/api/funciones/{esc.funcion_id}", headers=auth.admin)
    assert borrar.status_code == 409
    assert borrar.get_json()["error"]["mensaje"] == \
        "La función tiene ventas; use la opción de cancelar."
    precio = http.put(f"/api/funciones/{esc.funcion_id}", headers=auth.admin,
                      json={"precio": 25000})
    assert precio.status_code == 200
    estructura = http.put(f"/api/funciones/{esc.funcion_id}", headers=auth.admin,
                          json={"sala_id": esc.sala_id})
    assert estructura.status_code == 409
    assert estructura.get_json()["error"]["codigo"] == "FUNCION_CON_VENTAS"
