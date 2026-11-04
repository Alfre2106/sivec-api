"""Funciones, cartelera y mapa de asientos (CA-01, CA-02, CA-03)."""

from datetime import timedelta

from app.utils.tiempo import a_iso_bogota, ahora_utc
from tests.utilidades import (
    comprar, estado_asiento, filas_sql, reservar, valor_sql, vencer_reservas,
)


def _crear_pelicula_y_sala(http, auth, filas=3, por_fila=4):
    pelicula = http.post("/api/peliculas", headers=auth.admin, json={
        "titulo": "Película de prueba", "duracion_min": 100}).get_json()["pelicula"]
    sala = http.post("/api/salas", headers=auth.admin, json={
        "nombre": "Sala de prueba", "filas": filas,
        "asientos_por_fila": por_fila}).get_json()["sala"]
    return pelicula, sala


def test_ca01_crear_funcion_genera_todos_sus_asientos_disponibles(app, http, auth):
    """CA-01: al crear la función se generan filas A.. y números 1..N, todos disponibles."""
    pelicula, sala = _crear_pelicula_y_sala(http, auth)
    assert sala["capacidad"] == 12

    respuesta = http.post("/api/funciones", headers=auth.admin, json={
        "pelicula_id": pelicula["id"], "sala_id": sala["id"],
        "inicio": a_iso_bogota(ahora_utc() + timedelta(days=1)),
        "precio": 25000})
    assert respuesta.status_code == 201
    funcion = respuesta.get_json()["funcion"]
    assert funcion["capacidad"] == 12
    assert funcion["asientos_disponibles"] == 12
    assert funcion["estado"] == "activa"

    por_fila = filas_sql(
        app, "SELECT fila, count(*) FROM asientos_funcion "
             "WHERE funcion_id = :f GROUP BY fila ORDER BY fila", f=funcion["id"])
    assert por_fila == [("A", 4), ("B", 4), ("C", 4)]
    estados = filas_sql(
        app, "SELECT DISTINCT estado FROM asientos_funcion WHERE funcion_id = :f",
        f=funcion["id"])
    assert estados == [("disponible",)]


def test_ca01_funcion_solapada_no_deja_datos_a_medias(app, http, auth, crear_escenario):
    """CA-01 (rollback): una función rechazada no crea función ni asientos."""
    existente = crear_escenario(minutos=24 * 60)
    funciones_antes = valor_sql(app, "SELECT count(*) FROM funciones")
    asientos_antes = valor_sql(app, "SELECT count(*) FROM asientos_funcion")
    inicio = valor_sql(app, "SELECT inicio FROM funciones WHERE id = :f",
                       f=existente.funcion_id)

    respuesta = http.post("/api/funciones", headers=auth.admin, json={
        "pelicula_id": existente.pelicula_id, "sala_id": existente.sala_id,
        "inicio": inicio.isoformat(), "precio": 20000})

    assert respuesta.status_code == 409
    error = respuesta.get_json()["error"]
    assert error["codigo"] == "FUNCION_SOLAPADA"
    assert error["detalle"]["funcion_en_conflicto"] == existente.funcion_id
    assert valor_sql(app, "SELECT count(*) FROM funciones") == funciones_antes
    assert valor_sql(app, "SELECT count(*) FROM asientos_funcion") == asientos_antes


def test_ca02_cartelera_solo_funciones_activas_y_futuras(app, http, auth, crear_escenario):
    """CA-02: la cartelera pública excluye pasadas, canceladas y de películas inactivas."""
    futura = crear_escenario(minutos=24 * 60)
    pasada = crear_escenario(minutos=-300)          # ya terminó
    cancelada = crear_escenario(minutos=2 * 24 * 60)
    inactiva = crear_escenario(minutos=3 * 24 * 60)

    assert http.post(f"/api/funciones/{cancelada.funcion_id}/cancelar",
                     headers=auth.admin, json={"motivo": "prueba"}).status_code == 200
    assert http.delete(f"/api/peliculas/{inactiva.pelicula_id}",
                       headers=auth.admin).status_code == 200

    publicas = http.get("/api/funciones").get_json()["funciones"]
    assert {f["id"] for f in publicas} == {futura.funcion_id}
    assert publicas[0]["asientos_disponibles"] == futura.capacidad

    # Filtros por película y por día (hora de Bogotá).
    por_pelicula = http.get(f"/api/funciones?pelicula_id={futura.pelicula_id}")
    assert [f["id"] for f in por_pelicula.get_json()["funciones"]] == [futura.funcion_id]
    dia = a_iso_bogota(ahora_utc() + timedelta(days=1))[:10]
    por_dia = http.get(f"/api/funciones?fecha={dia}")
    assert futura.funcion_id in [f["id"] for f in por_dia.get_json()["funciones"]]

    # ?todas=1 solo lo respeta si quien pregunta es administrador.
    sin_permiso = http.get("/api/funciones?todas=1").get_json()["funciones"]
    assert {f["id"] for f in sin_permiso} == {futura.funcion_id}
    como_admin = http.get("/api/funciones?todas=1", headers=auth.admin)
    assert {f["id"] for f in como_admin.get_json()["funciones"]} == {
        futura.funcion_id, pasada.funcion_id, cancelada.funcion_id,
        inactiva.funcion_id}

    # El detalle público sí muestra funciones ya terminadas, con su estado real.
    detalle = http.get(f"/api/funciones/{pasada.funcion_id}").get_json()["funcion"]
    assert detalle["estado"] == "finalizada"


def test_ca03_mapa_de_asientos_con_estados_reales(app, http, auth, crear_escenario):
    """CA-03: el mapa refleja disponible/reservado/vendido y marca 'mio' solo al dueño."""
    esc = crear_escenario()
    a_reservado, a_vencido, a_vendido = esc.asientos[0], esc.asientos[1], esc.asientos[2]

    assert reservar(http, auth.cliente, esc.funcion_id, [a_reservado]).status_code == 201
    assert reservar(http, auth.otro_cliente, esc.funcion_id, [a_vencido]).status_code == 201
    vencer_reservas(app, [a_vencido])    # venció, pero el job aún no corrió
    assert comprar(http, auth.otro_cliente, esc.funcion_id, [a_vendido]).status_code == 201

    def mapa(cabecera=None):
        r = http.get(f"/api/funciones/{esc.funcion_id}/asientos",
                     headers=cabecera or {})
        assert r.status_code == 200
        cuerpo = r.get_json()
        assert cuerpo["funcion_id"] == esc.funcion_id
        assert cuerpo["estado_funcion"] == "activa"
        assert cuerpo["precio"] == esc.precio
        assert [f["fila"] for f in cuerpo["filas"]] == ["A", "B", "C"]
        return {a["id"]: a for f in cuerpo["filas"] for a in f["asientos"]}

    anonimo = mapa()
    assert len(anonimo) == esc.capacidad
    assert anonimo[a_reservado]["estado"] == "reservado"
    assert anonimo[a_vendido]["estado"] == "vendido"
    # Reserva vencida => se muestra disponible aunque la base aún diga "reservado".
    assert estado_asiento(app, a_vencido) == "reservado"
    assert anonimo[a_vencido]["estado"] == "disponible"
    assert not any(a["mio"] for a in anonimo.values())
    assert not any("vence_en" in a for a in anonimo.values())

    propio = mapa(auth.cliente)
    assert propio[a_reservado]["mio"] is True
    assert "vence_en" in propio[a_reservado]
    assert propio[a_vendido]["mio"] is False
    assert sum(1 for a in propio.values() if a["mio"]) == 1
