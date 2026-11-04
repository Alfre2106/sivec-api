"""Concurrencia con PostgreSQL real (CA-10, RNF-07).

Cada prueba lanza varios hilos que esperan en un `threading.Barrier` y disparan
su petición HTTP al mismo tiempo. Cada hilo usa su propio cliente y, por lo
tanto, su propia conexión y transacción. La garantía la dan los bloqueos de fila
(SELECT ... FOR UPDATE) de PostgreSQL; por eso NO sirve SQLite aquí.
"""

import threading
from collections import Counter

import pytest

from tests.utilidades import (
    codigos_de, comprar, estado_asiento, filas_sql, reservar, valor_sql, validar,
)

pytestmark = pytest.mark.concurrencia

TIEMPO_MAXIMO = 60  # segundos; si algo se bloquea (deadlock) la prueba falla


def correr_en_paralelo(app, tareas):
    """Ejecuta cada tarea(cliente_http) en su hilo, arrancando todas a la vez.

    Devuelve la lista de respuestas en el mismo orden que `tareas`. Si un hilo
    lanza una excepción, se vuelve a lanzar aquí para que la prueba falle.
    """
    barrera = threading.Barrier(len(tareas))
    respuestas = [None] * len(tareas)
    errores = []

    def trabajo(posicion, tarea):
        try:
            cliente = app.test_client()
            barrera.wait(timeout=TIEMPO_MAXIMO)     # salen todos juntos
            respuestas[posicion] = tarea(cliente)
        except Exception as error:                  # noqa: BLE001
            errores.append(error)

    hilos = [threading.Thread(target=trabajo, args=(i, t))
             for i, t in enumerate(tareas)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=TIEMPO_MAXIMO)
    assert not any(h.is_alive() for h in hilos), "Posible bloqueo (deadlock)"
    assert not errores, f"Error dentro de un hilo: {errores[0]!r}"
    return respuestas


def _codigos(respuestas):
    return Counter(r.status_code for r in respuestas)


@pytest.mark.parametrize("hilos", [2, 6])
def test_ca10_reservas_simultaneas_del_mismo_asiento_solo_una_gana(
        app, auth, crear_escenario, hilos):
    """CA-10: N reservas simultáneas del MISMO asiento => una sola se confirma."""
    esc = crear_escenario()
    cabeceras = [auth.cliente, auth.otro_cliente, auth.taquillero]

    for ronda in range(3):                       # varias rondas, asientos distintos
        asiento = esc.asientos[ronda]
        tareas = [
            (lambda c, h=cabeceras[i % 3]: reservar(c, h, esc.funcion_id, [asiento]))
            for i in range(hilos)
        ]

        respuestas = correr_en_paralelo(app, tareas)

        assert _codigos(respuestas) == Counter({201: 1, 409: hilos - 1})
        for r in respuestas:
            if r.status_code == 409:
                assert r.get_json()["error"]["codigo"] == "ASIENTO_NO_DISPONIBLE"
        assert estado_asiento(app, asiento) == "reservado"
        assert valor_sql(app, "SELECT count(*) FROM reservas "
                              "WHERE asiento_id = :a AND estado = 'activa'",
                         a=asiento) == 1


def test_ca10_reservas_con_asientos_cruzados_no_se_bloquean_entre_si(
        app, auth, crear_escenario):
    """CA-10: pedidos con asientos en distinto orden no causan deadlock (se bloquea por id)."""
    esc = crear_escenario()
    a, b, c = esc.asientos[:3]
    tareas = [
        lambda cl: reservar(cl, auth.cliente, esc.funcion_id, [a, b]),
        lambda cl: reservar(cl, auth.otro_cliente, esc.funcion_id, [c, b]),   # orden invertido
    ]

    respuestas = correr_en_paralelo(app, tareas)

    assert _codigos(respuestas) == Counter({201: 1, 409: 1})
    # Todo o nada: el asiento "c" o el "a" solo está reservado si su pedido ganó.
    reservados = {x for x in (a, b, c) if estado_asiento(app, x) == "reservado"}
    assert reservados in ({a, b}, {c, b})


def test_ca10_compras_simultaneas_de_los_mismos_asientos_solo_una_se_aprueba(
        app, auth, crear_escenario):
    """CA-10: dos compras simultáneas de los mismos asientos => una sola vende."""
    esc = crear_escenario()
    elegidos = esc.asientos[:2]
    tareas = [
        lambda c: comprar(c, auth.cliente, esc.funcion_id, elegidos),
        lambda c: comprar(c, auth.taquillero, esc.funcion_id, elegidos,
                          metodo_pago="efectivo", cliente={"nombre": "Walk In"}),
    ]

    respuestas = correr_en_paralelo(app, tareas)

    assert _codigos(respuestas) == Counter({201: 1, 409: 1})
    perdedora = next(r for r in respuestas if r.status_code == 409)
    assert perdedora.get_json()["error"]["codigo"] == "ASIENTO_NO_DISPONIBLE"
    assert valor_sql(app, "SELECT count(*) FROM compras WHERE estado_pago = 'aprobado'") == 1
    assert valor_sql(app, "SELECT count(*) FROM entradas") == 2
    assert all(estado_asiento(app, a) == "vendido" for a in elegidos)
    # La compra perdedora no dejó clientes huérfanos ni compras a medias.
    assert valor_sql(app, "SELECT count(*) FROM compras") == 1
    assert valor_sql(app, "SELECT count(*) FROM clientes WHERE nombre = 'Walk In'") in (0, 1)
    codigos = [c for (c,) in filas_sql(app, "SELECT codigo FROM entradas")]
    assert len(set(codigos)) == 2


def test_ca10_compras_con_asientos_solapados_una_sola_gana(app, auth, crear_escenario):
    """CA-10: compras que comparten UN asiento: una gana completa, la otra no vende nada."""
    esc = crear_escenario()
    a, b, c = esc.asientos[:3]
    tareas = [
        lambda cl: comprar(cl, auth.cliente, esc.funcion_id, [a, b]),
        lambda cl: comprar(cl, auth.otro_cliente, esc.funcion_id, [c, b]),
    ]

    respuestas = correr_en_paralelo(app, tareas)

    assert _codigos(respuestas) == Counter({201: 1, 409: 1})
    assert valor_sql(app, "SELECT count(*) FROM entradas") == 2
    vendidos = {x for x in (a, b, c) if estado_asiento(app, x) == "vendido"}
    assert vendidos in ({a, b}, {c, b})
    assert len(vendidos) == 2           # el asiento del perdedor sigue libre


@pytest.mark.parametrize("hilos", [2, 6])
def test_ca10_validaciones_simultaneas_del_mismo_codigo(app, auth, crear_escenario, hilos):
    """CA-10 / RN-07: una validación da 'valida' y las demás 'ya_usada' (200 todas)."""
    esc = crear_escenario(minutos=30)
    codigo = codigos_de(comprar(app.test_client(), auth.cliente,
                                esc.funcion_id, esc.asientos[:1]))[0]
    cabeceras = [auth.taquillero, auth.admin]
    tareas = [(lambda c, h=cabeceras[i % 2]: validar(c, h, codigo))
              for i in range(hilos)]

    respuestas = correr_en_paralelo(app, tareas)

    assert {r.status_code for r in respuestas} == {200}
    resultados = Counter(r.get_json()["resultado"] for r in respuestas)
    assert resultados == Counter({"valida": 1, "ya_usada": hilos - 1})
    assert valor_sql(app, "SELECT estado FROM entradas WHERE codigo = :c", c=codigo) == "usada"
    assert valor_sql(app, "SELECT count(*) FROM validaciones") == hilos      # todos quedan
    assert valor_sql(app, "SELECT count(*) FROM auditoria "
                          "WHERE accion = 'validar_entrada'") == 1


@pytest.mark.parametrize("ronda", range(3))
def test_ca10_compra_y_cancelacion_simultaneas_no_dejan_entradas_activas(
        app, auth, crear_escenario, ronda):
    """CA-10 / RN-10: comprar mientras se cancela nunca deja una entrada vigente."""
    esc = crear_escenario()
    tareas = [
        lambda c: c.post(f"/api/funciones/{esc.funcion_id}/cancelar",
                         headers=auth.admin, json={"motivo": "carrera"}),
        lambda c: comprar(c, auth.cliente, esc.funcion_id, esc.asientos[:2]),
    ]

    cancelacion, compra = correr_en_paralelo(app, tareas)

    assert cancelacion.status_code == 200
    assert compra.status_code in (201, 409)
    assert valor_sql(app, "SELECT estado FROM funciones WHERE id = :f",
                     f=esc.funcion_id) == "cancelada"
    # Si la compra alcanzó a entrar antes, la cancelación debió anular sus entradas.
    assert valor_sql(app, "SELECT count(*) FROM entradas WHERE estado = 'activa'") == 0
    if compra.status_code == 201:
        assert valor_sql(app, "SELECT count(*) FROM entradas WHERE estado = 'anulada'") == 2
    else:
        assert valor_sql(app, "SELECT count(*) FROM entradas") == 0
