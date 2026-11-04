"""Reportes e indicadores (CA-11): las cifras coinciden con los registros."""

import csv
import io
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.reservas_service import expirar_reservas_vencidas
from app.utils.tiempo import ZONA_BOGOTA
from tests.utilidades import (
    comprar, ejecutar_sql, reservar, valor_sql, validar, vencer_reservas,
)


@pytest.fixture
def datos(app, http, auth, crear_escenario):
    """Escenario con cifras conocidas.

    A (precio 20000, en 24 h): cliente compra 3, otro cliente compra 2, un pago
        rechazado (queda 1 reserva activa) y 1 reserva que vence y se expira.
    B (precio 30000, en 24 h): cliente compra 1 y luego se CANCELA la función.
    C (precio 20000, en 30 min): otro cliente compra 1; se valida (usada) y se
        registran 1 código inexistente y 1 reintento ya usado.
    """
    a = crear_escenario(minutos=24 * 60, precio=20000)
    b = crear_escenario(minutos=24 * 60, precio=30000)
    c = crear_escenario(minutos=30, precio=20000)

    assert comprar(http, auth.cliente, a.funcion_id, a.asientos[:3]).status_code == 201
    assert comprar(http, auth.otro_cliente, a.funcion_id, a.asientos[3:5]).status_code == 201
    assert comprar(http, auth.cliente, a.funcion_id, [a.asientos[5]],
                   resultado="rechazado").status_code == 402
    assert reservar(http, auth.taquillero, a.funcion_id, [a.asientos[6]]).status_code == 201
    vencer_reservas(app, [a.asientos[6]])
    with app.app_context():
        assert expirar_reservas_vencidas() == 1

    assert comprar(http, auth.cliente, b.funcion_id, [b.asientos[0]]).status_code == 201
    assert http.post(f"/api/funciones/{b.funcion_id}/cancelar", headers=auth.admin,
                     json={"motivo": "prueba"}).status_code == 200

    venta_c = comprar(http, auth.otro_cliente, c.funcion_id, [c.asientos[0]])
    codigo_c = venta_c.get_json()["entradas"][0]["codigo"]
    assert validar(http, auth.taquillero, codigo_c).get_json()["resultado"] == "valida"
    validar(http, auth.taquillero, codigo_c)                 # ya_usada
    validar(http, auth.taquillero, "SIV-NOEXISTE0000")       # invalida
    return SimpleNamespace(a=a, b=b, c=c)


def reporte(http, auth, ruta):
    respuesta = http.get(f"/api/reportes/{ruta}", headers=auth.admin)
    assert respuesta.status_code == 200, respuesta.get_json()
    return respuesta.get_json()


def test_ca11_resumen_coincide_con_los_registros(app, http, auth, datos):
    """CA-11: ventas, ingresos anulados, entradas, funciones activas y ocupación."""
    r = reporte(http, auth, "resumen?dias=30")

    assert r["ventas_totales"] == 120000            # 60000 + 40000 + 20000 (B no cuenta)
    assert r["ingresos_anulados"] == 30000          # compra de la función cancelada
    assert r["entradas_vendidas"] == 6              # 3 + 2 + 1 (la anulada no cuenta)
    assert r["entradas_anuladas"] == 1
    assert r["funciones_activas"] == 2              # A y C (B está cancelada)
    assert r["ocupacion_promedio"] == 25.0          # (5/12 + 1/12) / 2
    assert r["usuarios_total"] == 4
    assert r["periodo"]["dias"] == 30
    # La compra rechazada (20000) nunca suma.
    assert valor_sql(app, "SELECT COALESCE(SUM(total),0) FROM compras "
                          "WHERE estado_pago = 'rechazado'") == 20000
    # Contra SQL independiente:
    assert r["ventas_totales"] == valor_sql(
        app, "SELECT SUM(c.total) FROM compras c JOIN funciones f ON f.id = c.funcion_id "
             "WHERE c.estado_pago = 'aprobado' AND f.estado <> 'cancelada'")
    # Sin datos en el periodo anterior no hay variación que calcular.
    assert set(r["variacion"].values()) == {None}


def test_ca11_variacion_contra_el_periodo_anterior(app, http, auth, datos):
    """CA-11: con datos previos, la variación porcentual se calcula bien."""
    # Una compra de 40000 (2 entradas) ocurrió hace 40 días: periodo anterior.
    ejecutar_sql(app, "UPDATE compras SET creado_en = now() - interval '40 days' "
                      "WHERE total = 40000 AND estado_pago = 'aprobado'")

    r = reporte(http, auth, "resumen?dias=30")

    assert r["ventas_totales"] == 80000
    assert r["variacion"]["ventas_totales"] == 100.0       # 40000 -> 80000
    assert r["variacion"]["entradas_vendidas"] == 100.0    # 2 -> 4
    assert r["variacion"]["ingresos_anulados"] is None     # antes no había


def test_ca11_ventas_por_mes_con_ceros(app, http, auth, datos):
    """CA-11: serie mensual en hora de Bogotá, con ceros en meses sin datos."""
    r = reporte(http, auth, "ventas-por-mes?meses=6")

    assert len(r["serie"]) == 6
    actual = datetime.now(ZONA_BOGOTA).strftime("%Y-%m")
    por_mes = {fila["mes"]: fila for fila in r["serie"]}
    assert r["serie"][-1]["mes"] == actual
    assert por_mes[actual] == {"mes": actual, "ventas": 120000, "entradas": 6}
    assert all(f["ventas"] == 0 and f["entradas"] == 0
               for f in r["serie"] if f["mes"] != actual)


def test_ca11_ventas_ocupacion_y_asistencia_por_funcion(app, http, auth, datos):
    """CA-11: por función, sin la cancelada; ocupación = vendidos / capacidad."""
    ventas = {f["funcion_id"]: f for f in reporte(http, auth, "ventas-por-funcion")["funciones"]}
    assert set(ventas) == {datos.a.funcion_id, datos.c.funcion_id}
    assert ventas[datos.a.funcion_id]["entradas_vendidas"] == 5
    assert ventas[datos.a.funcion_id]["ingresos"] == 100000
    assert ventas[datos.c.funcion_id]["ingresos"] == 20000

    ocupacion = {f["funcion_id"]: f for f in reporte(http, auth, "ocupacion")["funciones"]}
    assert ocupacion[datos.a.funcion_id] == {
        "funcion_id": datos.a.funcion_id, "pelicula": "Película 1",
        "sala": "Sala 1", "inicio": ocupacion[datos.a.funcion_id]["inicio"],
        "capacidad": 12, "vendidos": 5, "reservados_vigentes": 1, "porcentaje": 41.7}
    assert ocupacion[datos.c.funcion_id]["porcentaje"] == 8.3

    asistencia = reporte(http, auth, "asistencia")
    assert asistencia["global"] == {"entradas_vendidas": 6, "entradas_usadas": 1,
                                    "porcentaje": 16.7}
    por_funcion = {f["funcion_id"]: f for f in asistencia["por_funcion"]}
    assert por_funcion[datos.c.funcion_id]["porcentaje"] == 100.0
    assert por_funcion[datos.a.funcion_id]["porcentaje"] == 0.0


def test_ca11_ranking_de_peliculas(http, auth, datos):
    """CA-11: ranking por entradas vendidas con % de participación."""
    mas = reporte(http, auth, "peliculas-ranking?orden=desc&limite=2")
    assert mas["total_entradas"] == 6
    assert [(p["pelicula"], p["entradas_vendidas"], p["participacion"])
            for p in mas["ranking"]] == [("Película 1", 5, 83.3), ("Película 3", 1, 16.7)]

    menos = reporte(http, auth, "peliculas-ranking?orden=asc&limite=1")
    assert menos["ranking"][0]["pelicula"] == "Película 2"       # 0 entradas vendidas
    assert menos["ranking"][0]["entradas_vendidas"] == 0


def test_ca11_reservas_vencidas_e_intentos_rechazados(http, auth, datos):
    """CA-11: tasa de pérdida de reservas y conteo de validaciones rechazadas."""
    reservas = reporte(http, auth, "reservas-vencidas")
    assert reservas == {"total_reservas": 9, "expiradas": 1, "convertidas": 7,
                        "canceladas": 0, "activas": 1, "tasa_perdida": 11.1}

    intentos = reporte(http, auth, "intentos-rechazados")
    assert intentos["total_rechazados"] == 2
    assert intentos["por_resultado"] == {"invalida": 1, "ya_usada": 1,
                                         "otra_funcion": 0, "anulada": 0}
    assert {u["resultado"] for u in intentos["ultimos"]} == {"invalida", "ya_usada"}
    assert intentos["ultimos"][0]["taquillero"] == "Taquillero Prueba"
    assert {"fecha", "codigo_leido"} <= set(intentos["ultimos"][0])


def test_ca11_filtros_de_fecha(http, auth, datos):
    """CA-11: los filtros desde/hasta se validan y filtran."""
    hoy = datetime.now(ZONA_BOGOTA).strftime("%Y-%m-%d")
    assert reporte(http, auth, f"reservas-vencidas?desde={hoy}&hasta={hoy}")["total_reservas"] == 9
    assert reporte(http, auth, "reservas-vencidas?desde=2020-01-01&hasta=2020-01-31"
                   )["total_reservas"] == 0

    for ruta, codigo in [
        ("ventas-por-funcion?desde=2026-12-01&hasta=2026-11-01", "RANGO_INVALIDO"),
        ("ventas-por-funcion?desde=2020-01-01&hasta=2026-11-01", "RANGO_MUY_AMPLIO"),
        ("ocupacion?desde=01-11-2026", "FECHA_INVALIDA"),
        ("resumen?dias=0", "DIAS_INVALIDOS"),
        ("ventas-por-mes?meses=25", "MESES_INVALIDOS"),
        ("peliculas-ranking?orden=raro", "ORDEN_INVALIDO"),
        ("peliculas-ranking?limite=0", "LIMITE_INVALIDO"),
        ("exportar?tipo=otro", "TIPO_INVALIDO"),
    ]:
        respuesta = http.get(f"/api/reportes/{ruta}", headers=auth.admin)
        assert respuesta.status_code == 422, ruta
        assert respuesta.get_json()["error"]["codigo"] == codigo, ruta


def _leer_csv(respuesta):
    texto = respuesta.data.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(texto), delimiter=";"))


def test_ca11_exportar_csv(http, auth, datos):
    """CA-11: CSV UTF-8 con BOM, separador ';' y nombre sivec_<tipo>_<fecha>.csv."""
    respuesta = http.get("/api/reportes/exportar?tipo=ventas", headers=auth.admin)

    assert respuesta.status_code == 200
    assert respuesta.data.startswith(b"\xef\xbb\xbf")
    assert respuesta.mimetype == "text/csv"
    hoy = datetime.now(ZONA_BOGOTA).strftime("%Y-%m-%d")
    assert respuesta.headers["Content-Disposition"] == \
        f'attachment; filename="sivec_ventas_{hoy}.csv"'
    filas = _leer_csv(respuesta)
    assert filas[0][:3] == ["numero", "fecha", "cliente"]
    assert len(filas) == 1 + 4                      # 4 compras aprobadas
    ultima_col = filas[0].index("funcion_cancelada")
    assert sorted(f[ultima_col] for f in filas[1:]) == ["No", "No", "No", "Sí"]
    assert sum(int(f[filas[0].index("total")]) for f in filas[1:]) == 150000

    for tipo in ("ocupacion", "ranking", "validaciones"):
        otro = http.get(f"/api/reportes/exportar?tipo={tipo}", headers=auth.admin)
        assert otro.status_code == 200
        assert otro.headers["Content-Disposition"].startswith(
            f'attachment; filename="sivec_{tipo}_')


def test_ca11_csv_neutraliza_formulas(http, auth, datos):
    """Seguridad: un texto que empieza por = + - @ se exporta como texto, no fórmula."""
    for peligroso in ("=1+1", "+cmd", "-2+3", "@suma"):
        validar(http, auth.taquillero, peligroso)

    filas = _leer_csv(http.get("/api/reportes/exportar?tipo=validaciones",
                               headers=auth.admin))

    columna = filas[0].index("codigo_leido")
    leidos = [f[columna] for f in filas[1:]]
    for peligroso in ("=1+1", "+CMD", "-2+3", "@SUMA"):
        assert f"'{peligroso}" in leidos
        assert peligroso not in leidos
