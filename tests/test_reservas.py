"""Reservas y expiración (CA-04, CA-05, CA-06)."""

from datetime import datetime, timezone

import pytest

from app.services.reservas_service import expirar_reservas_vencidas
from tests.utilidades import (
    comprar, estado_asiento, filas_sql, reservar, valor_sql, vencer_reservas,
)


@pytest.mark.parametrize("ocupado_por", ["reservado", "vendido"])
def test_ca04_asiento_reservado_o_vendido_no_se_puede_seleccionar(
        app, http, auth, crear_escenario, ocupado_por):
    """CA-04 / RN-02: un asiento reservado o vendido se rechaza con 409 y la lista."""
    esc = crear_escenario()
    ocupado = esc.asientos[0]
    if ocupado_por == "reservado":
        assert reservar(http, auth.otro_cliente, esc.funcion_id, [ocupado]).status_code == 201
    else:
        assert comprar(http, auth.otro_cliente, esc.funcion_id, [ocupado]).status_code == 201

    respuesta = reservar(http, auth.cliente, esc.funcion_id, [ocupado])

    assert respuesta.status_code == 409
    error = respuesta.get_json()["error"]
    assert error["codigo"] == "ASIENTO_NO_DISPONIBLE"
    assert error["detalle"]["asientos_no_disponibles"] == [ocupado]


def test_ca04_reserva_todo_o_nada(app, http, auth, crear_escenario):
    """CA-04: si UN asiento no está disponible, no se reserva ninguno (rollback)."""
    esc = crear_escenario()
    libre, ocupado = esc.asientos[0], esc.asientos[1]
    assert reservar(http, auth.otro_cliente, esc.funcion_id, [ocupado]).status_code == 201

    respuesta = reservar(http, auth.cliente, esc.funcion_id, [libre, ocupado])

    assert respuesta.status_code == 409
    assert respuesta.get_json()["error"]["detalle"]["asientos_no_disponibles"] == [ocupado]
    assert estado_asiento(app, libre) == "disponible"
    assert valor_sql(app, "SELECT count(*) FROM reservas WHERE asiento_id = :a",
                     a=libre) == 0


def test_ca05_reservar_asientos_disponibles(app, http, auth, usuarios, crear_escenario):
    """CA-05 / RN-03: reservar deja los asientos 'reservado' por 5 minutos."""
    esc = crear_escenario()
    elegidos = esc.asientos[:3]

    respuesta = reservar(http, auth.cliente, esc.funcion_id, elegidos)

    assert respuesta.status_code == 201
    cuerpo = respuesta.get_json()
    assert [r["asiento_id"] for r in cuerpo["reservas"]] == elegidos
    assert {"id", "asiento_id", "fila", "numero"} <= set(cuerpo["reservas"][0])
    assert 290 <= cuerpo["segundos_restantes"] <= 300
    assert datetime.fromisoformat(cuerpo["vence_en"]).tzinfo is not None
    assert all(estado_asiento(app, a) == "reservado" for a in elegidos)
    assert valor_sql(app, "SELECT count(*) FROM reservas "
                          "WHERE estado = 'activa' AND usuario_id = :u",
                     u=usuarios.cliente.id) == 3
    # El taquillero también puede reservar (venta asistida).
    assert reservar(http, auth.taquillero, esc.funcion_id,
                    [esc.asientos[5]]).status_code == 201


def test_ca05_validaciones_de_la_solicitud(app, http, auth, crear_escenario):
    """CA-05: lista vacía, repetidos, más de 8, ids no enteros y función ajena."""
    esc = crear_escenario(filas=3, por_fila=4)
    otra = crear_escenario()

    assert reservar(http, auth.cliente, esc.funcion_id, []).status_code == 422
    assert reservar(http, auth.cliente, esc.funcion_id,
                    [esc.asientos[0]] * 2).status_code == 422
    assert http.post("/api/reservas", headers=auth.cliente, json={
        "funcion_id": esc.funcion_id, "asientos": ["x"]}).status_code == 422
    demasiados = http.post("/api/reservas", headers=auth.cliente, json={
        "funcion_id": esc.funcion_id, "asientos": list(range(1, 10))})
    assert demasiados.status_code == 422
    assert demasiados.get_json()["error"]["codigo"] == "DEMASIADOS_ASIENTOS"
    # Un asiento que pertenece a otra función se rechaza.
    ajeno = reservar(http, auth.cliente, esc.funcion_id, [otra.asientos[0]])
    assert ajeno.status_code == 422
    assert ajeno.get_json()["error"]["codigo"] == "ASIENTO_INVALIDO"
    assert estado_asiento(app, otra.asientos[0]) == "disponible"


def test_ca05_limite_de_reservas_activas_por_funcion(app, http, auth, crear_escenario):
    """CA-05: máximo 8 reservas activas por usuario en la misma función."""
    esc = crear_escenario(filas=3, por_fila=4)    # 12 asientos
    assert reservar(http, auth.cliente, esc.funcion_id, esc.asientos[:8]).status_code == 201

    novena = reservar(http, auth.cliente, esc.funcion_id, [esc.asientos[8]])

    assert novena.status_code == 409
    assert novena.get_json()["error"]["codigo"] == "LIMITE_RESERVAS"
    assert estado_asiento(app, esc.asientos[8]) == "disponible"


def test_ca05_no_se_reserva_en_funcion_iniciada(app, http, auth, crear_escenario):
    """RN-08: no se reserva en funciones ya iniciadas."""
    esc = crear_escenario(minutos=-10)
    respuesta = reservar(http, auth.cliente, esc.funcion_id, [esc.asientos[0]])
    assert respuesta.status_code == 409
    assert respuesta.get_json()["error"]["codigo"] == "FUNCION_NO_DISPONIBLE"


def test_ca06_reserva_vencida_libera_el_asiento(app, http, auth, crear_escenario):
    """CA-06 / RN-03: al vencer, el servicio de expiración devuelve el asiento."""
    esc = crear_escenario()
    a1, a2, vigente = esc.asientos[0], esc.asientos[1], esc.asientos[2]
    assert reservar(http, auth.cliente, esc.funcion_id, [a1, a2]).status_code == 201
    assert reservar(http, auth.otro_cliente, esc.funcion_id, [vigente]).status_code == 201
    vencer_reservas(app, [a1, a2])       # se modifica vence_en en la base

    with app.app_context():
        liberadas = expirar_reservas_vencidas()

    assert liberadas == 2
    assert estado_asiento(app, a1) == "disponible"
    assert estado_asiento(app, a2) == "disponible"
    assert estado_asiento(app, vigente) == "reservado"       # la vigente no se toca
    assert filas_sql(app, "SELECT DISTINCT estado FROM reservas "
                          "WHERE asiento_id = ANY(:a)", a=[a1, a2]) == [("expirada",)]
    # Una sola fila de auditoría con el resumen (no una por asiento).
    resumenes = filas_sql(app, "SELECT detalle FROM auditoria "
                               "WHERE accion = 'expirar_reservas'")
    assert len(resumenes) == 1 and resumenes[0][0] == {"liberadas": 2}
    # Una segunda ejecución no hace nada ni audita.
    with app.app_context():
        assert expirar_reservas_vencidas() == 0
    assert valor_sql(app, "SELECT count(*) FROM auditoria "
                          "WHERE accion = 'expirar_reservas'") == 1
    # Y el asiento liberado ya se puede reservar de nuevo.
    assert reservar(http, auth.otro_cliente, esc.funcion_id, [a1]).status_code == 201


def test_ca06_expiracion_perezosa_al_reservar(app, http, auth, usuarios, crear_escenario):
    """CA-06: aunque el job no haya corrido, reservar libera la vencida en su transacción."""
    esc = crear_escenario()
    asiento = esc.asientos[0]
    assert reservar(http, auth.cliente, esc.funcion_id, [asiento]).status_code == 201
    vencer_reservas(app, [asiento])

    assert reservar(http, auth.otro_cliente, esc.funcion_id, [asiento]).status_code == 201

    assert filas_sql(app, "SELECT usuario_id, estado FROM reservas "
                          "WHERE asiento_id = :a ORDER BY id", a=asiento) == [
        (usuarios.cliente.id, "expirada"), (usuarios.otro_cliente.id, "activa")]


def test_el_scheduler_no_arranca_en_modo_testing(app):
    """En configuración 'testing' el job de expiración NO se inicia (las pruebas lo invocan a mano)."""
    from app import scheduler
    assert app.config["TESTING"] is True
    assert scheduler._scheduler is None


def test_cancelar_reservas(app, http, auth, crear_escenario):
    """Cancelar: solo el dueño; 'volver' cancela todas las mías en la función."""
    esc = crear_escenario()
    r = reservar(http, auth.cliente, esc.funcion_id, esc.asientos[:3]).get_json()
    primera = r["reservas"][0]["id"]

    ajeno = http.delete(f"/api/reservas/{primera}", headers=auth.otro_cliente)
    assert ajeno.status_code == 403
    assert ajeno.get_json()["error"]["codigo"] == "RESERVA_AJENA"

    assert http.delete(f"/api/reservas/{primera}", headers=auth.cliente).status_code == 200
    assert estado_asiento(app, esc.asientos[0]) == "disponible"
    assert http.delete(f"/api/reservas/{primera}",
                       headers=auth.cliente).status_code == 409     # ya no está activa
    assert http.delete("/api/reservas/99999", headers=auth.cliente).status_code == 404

    mias = http.get(f"/api/reservas/mias?funcion_id={esc.funcion_id}", headers=auth.cliente)
    assert len(mias.get_json()["reservas"]) == 2

    todas = http.post("/api/reservas/cancelar", headers=auth.cliente,
                      json={"funcion_id": esc.funcion_id})
    assert todas.get_json() == {"canceladas": 2}
    assert all(estado_asiento(app, a) == "disponible" for a in esc.asientos[:3])
