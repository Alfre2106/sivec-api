"""Tiempos de respuesta (RNF-03: cada operación principal en menos de 3 segundos).

Se carga volumen realista (sala máxima de 780 asientos, 6.000 compras, 12.000
entradas, 6.000 validaciones, 200 asientos reservados) y se mide cada endpoint
a través de la capa HTTP. Para ver la tabla de tiempos:

    python -m pytest tests/test_rendimiento.py -v -s
"""

import time

import pytest

from tests.utilidades import comprar, ejecutar_sql, reservar, validar

LIMITE_SEGUNDOS = 3.0

pytestmark = pytest.mark.rendimiento


def _cargar_volumen(app, usuarios, esc):
    ejecutar_sql(app, """
        INSERT INTO compras (cliente_id, usuario_id, funcion_id, total, metodo_pago,
                             estado_pago, creado_en)
        SELECT :cli, :usr, :f, 20000, 'tarjeta', 'aprobado',
               now() - random() * interval '700 days'
        FROM generate_series(1, 6000)""",
        cli=usuarios.cliente.cliente_id, usr=usuarios.cliente.id, f=esc.funcion_id)
    ejecutar_sql(app, """
        INSERT INTO entradas (codigo, compra_id, funcion_id, asiento_id, estado)
        SELECT 'PERF-' || c.id || '-' || k, c.id, c.funcion_id, :a,
               (CASE WHEN random() < 0.1 THEN 'usada' ELSE 'activa' END)::estado_entrada
        FROM compras c CROSS JOIN generate_series(1, 2) k""", a=esc.asientos[0])
    ejecutar_sql(app, """
        INSERT INTO validaciones (entrada_id, codigo_leido, taquillero_id, fecha,
                                  resultado, detalle)
        SELECT NULL, 'PERF' || g, :t, now() - random() * interval '700 days',
               'invalida'::resultado_validacion, 'perf'
        FROM generate_series(1, 6000) g""", t=usuarios.taquillero.id)
    # 200 asientos reservados y vigentes: el mapa debe calcular su estado efectivo.
    reservados = esc.asientos[400:600]
    ejecutar_sql(app, "UPDATE asientos_funcion SET estado = 'reservado' "
                      "WHERE id = ANY(:ids)", ids=reservados)
    ejecutar_sql(app, """
        INSERT INTO reservas (asiento_id, usuario_id, reservado_en, vence_en, estado)
        SELECT id, :u, now(), now() + interval '5 minutes', 'activa'
        FROM asientos_funcion WHERE id = ANY(:ids)""",
        u=usuarios.otro_cliente.id, ids=reservados)
    ejecutar_sql(app, "ANALYZE compras, entradas, validaciones, reservas")


def test_rnf03_endpoints_principales_responden_en_menos_de_3_segundos(
        app, http, auth, usuarios, crear_escenario):
    esc = crear_escenario(minutos=30, filas=26, por_fila=30)
    assert len(esc.asientos) == 780
    _cargar_volumen(app, usuarios, esc)

    tiempos = {}

    def medir(nombre, peticion, esperado=200):
        inicio = time.perf_counter()
        respuesta = peticion()
        tiempos[nombre] = time.perf_counter() - inicio
        assert respuesta.status_code == esperado, (nombre, respuesta.get_json())
        return respuesta

    # --- Operaciones del cliente y de la puerta ---
    mapa = medir("mapa de asientos (780, anónimo)",
                 lambda: http.get(f"/api/funciones/{esc.funcion_id}/asientos"))
    assert sum(len(f["asientos"]) for f in mapa.get_json()["filas"]) == 780
    medir("mapa de asientos (780, con sesión)",
          lambda: http.get(f"/api/funciones/{esc.funcion_id}/asientos", headers=auth.cliente))
    medir("reservar 8 asientos",
          lambda: reservar(http, auth.cliente, esc.funcion_id, esc.asientos[10:18]), 201)
    compra = medir("comprar 8 asientos",
                   lambda: comprar(http, auth.cliente, esc.funcion_id, esc.asientos[20:28]), 201)
    codigo = compra.get_json()["entradas"][0]["codigo"]
    medir("validar entrada", lambda: validar(http, auth.taquillero, codigo))
    medir("cartelera (GET /funciones)", lambda: http.get("/api/funciones"))
    medir("mis compras (cliente con 6.000 compras)",
          lambda: http.get("/api/mis-compras", headers=auth.cliente))
    medir("ventas (administrador, historial completo)",
          lambda: http.get("/api/ventas", headers=auth.admin))

    # --- Reportes (con 6.000 compras y 12.000 entradas) ---
    for ruta in ("resumen?dias=30", "ventas-por-mes?meses=12", "ventas-por-funcion",
                 "ocupacion", "peliculas-ranking", "reservas-vencidas", "asistencia",
                 "intentos-rechazados", "exportar?tipo=ventas", "exportar?tipo=validaciones"):
        medir(f"reporte {ruta}", lambda r=ruta: http.get(f"/api/reportes/{r}", headers=auth.admin))

    print("\n\nRNF-03 — tiempos de respuesta (límite 3,0 s)")
    for nombre, segundos in sorted(tiempos.items(), key=lambda x: -x[1]):
        print(f"  {segundos * 1000:8.0f} ms   {nombre}")
    lentos = {n: round(s, 2) for n, s in tiempos.items() if s >= LIMITE_SEGUNDOS}
    assert not lentos, f"Superan {LIMITE_SEGUNDOS} s: {lentos}"
