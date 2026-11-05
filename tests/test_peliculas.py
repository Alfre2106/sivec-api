"""Clasificación y póster de las películas, y su carga con el seed."""

import pytest

from app.services.peliculas_service import CLASIFICACIONES_PERMITIDAS
from tests.utilidades import comprar, ejecutar_sql, filas_sql, valor_sql

VALIDAS = ["Todo público", "Mayores de 7", "Mayores de 12", "Mayores de 15", "Mayores de 18"]
INVALIDAS = ["A", "B", "C", "todo público", "Mayores de 21", "Mayores de 12 ", "", 12, ["Todo público"]]


def test_los_valores_permitidos_son_exactamente_los_cinco_acordados():
    assert list(CLASIFICACIONES_PERMITIDAS) == VALIDAS


@pytest.mark.parametrize("valor", VALIDAS)
def test_post_y_put_aceptan_cada_clasificacion_permitida(http, auth, valor):
    creada = http.post("/api/peliculas", headers=auth.admin,
                       json={"titulo": f"Peli {valor}", "clasificacion": valor})
    assert creada.status_code == 201
    assert creada.get_json()["pelicula"]["clasificacion"] == valor

    pelicula_id = creada.get_json()["pelicula"]["id"]
    editada = http.put(f"/api/peliculas/{pelicula_id}", headers=auth.admin,
                       json={"clasificacion": "Mayores de 18" if valor != "Mayores de 18" else "Mayores de 7"})
    assert editada.status_code == 200
    assert editada.get_json()["pelicula"]["clasificacion"] in VALIDAS


@pytest.mark.parametrize("valor", INVALIDAS)
def test_post_y_put_rechazan_clasificaciones_no_permitidas(app, http, auth, valor):
    rechazo = http.post("/api/peliculas", headers=auth.admin,
                        json={"titulo": "Mala", "clasificacion": valor})
    assert rechazo.status_code == 422
    error = rechazo.get_json()["error"]
    assert error["codigo"] == "CLASIFICACION_INVALIDA"
    for permitido in VALIDAS:          # el mensaje dice cuáles sí sirven
        assert permitido in error["mensaje"]
    assert valor_sql(app, "SELECT count(*) FROM peliculas") == 0

    existente = http.post("/api/peliculas", headers=auth.admin,
                          json={"titulo": "Buena", "clasificacion": "Mayores de 7"})
    pelicula_id = existente.get_json()["pelicula"]["id"]
    rechazo_put = http.put(f"/api/peliculas/{pelicula_id}", headers=auth.admin,
                           json={"clasificacion": valor})
    assert rechazo_put.status_code == 422
    assert rechazo_put.get_json()["error"]["codigo"] == "CLASIFICACION_INVALIDA"
    assert valor_sql(app, "SELECT clasificacion FROM peliculas WHERE id = :i",
                     i=pelicula_id) == "Mayores de 7"      # no cambió


def test_la_clasificacion_sigue_siendo_opcional(http, auth):
    """Sin clasificación se crea igual; y un PUT que no la menciona no la borra."""
    creada = http.post("/api/peliculas", headers=auth.admin, json={"titulo": "Sin clase"})
    assert creada.status_code == 201 and creada.get_json()["pelicula"]["clasificacion"] is None
    pelicula_id = creada.get_json()["pelicula"]["id"]
    http.put(f"/api/peliculas/{pelicula_id}", headers=auth.admin, json={"clasificacion": "Mayores de 15"})
    otro = http.put(f"/api/peliculas/{pelicula_id}", headers=auth.admin, json={"genero": "Drama"})
    assert otro.get_json()["pelicula"]["clasificacion"] == "Mayores de 15"


def test_solo_el_administrador_cambia_la_clasificacion(http, auth):
    assert http.post("/api/peliculas", headers=auth.cliente,
                     json={"titulo": "X", "clasificacion": "Todo público"}).status_code == 403


# --- Seed ---------------------------------------------------------------

POSTERS_ESPERADOS = {
    "Intensa-Mente 2": ("/posters/intensamente-2.jpg", "Todo público"),
    "Deadpool & Wolverine": ("/posters/deadpool-wolverine.jpg", "Mayores de 15"),
    "La Odisea": ("/posters/la-odisea.jpg", "Mayores de 12"),
    "Moana": ("/posters/moana.jpg", "Todo público"),
    "La Noche del Demonio": ("/posters/la-noche-del-demonio.jpg", "Mayores de 15"),
    "Scary Movie": ("/posters/scary-movie.jpg", "Mayores de 15"),
    "Spider-Man: Brand New Day": ("/posters/spiderman-brand-new-day.webp", "Mayores de 12"),
}


def _peliculas(app):
    return {t: (p, c) for t, p, c in filas_sql(
        app, "SELECT titulo, poster_url, clasificacion FROM peliculas")}


def test_el_seed_carga_los_posters_y_clasificaciones_acordados(app):
    from scripts.seed import ejecutar_seed
    with app.app_context():
        ejecutar_seed()
    assert _peliculas(app) == POSTERS_ESPERADOS


def test_el_seed_actualiza_por_titulo_sin_borrar_ventas_y_es_idempotente(app, http, auth):
    from scripts.seed import ejecutar_seed
    with app.app_context():
        ejecutar_seed()

    # Una compra real de un cliente sobre una función de Moana.
    funcion_moana, asiento = filas_sql(
        app, "SELECT f.id, a.id FROM funciones f JOIN peliculas p ON p.id = f.pelicula_id "
             "JOIN asientos_funcion a ON a.funcion_id = f.id "
             "WHERE p.titulo = 'Moana' AND f.estado = 'activa' AND f.inicio > now() "
             "AND a.estado = 'disponible' ORDER BY f.id, a.id LIMIT 1")[0]
    assert comprar(http, auth.cliente, funcion_moana, [asiento]).status_code == 201

    antes = {
        "ids": filas_sql(app, "SELECT id, titulo FROM peliculas ORDER BY id"),
        "compras": valor_sql(app, "SELECT count(*) FROM compras"),
        "entradas": valor_sql(app, "SELECT count(*) FROM entradas"),
        "reservas": valor_sql(app, "SELECT count(*) FROM reservas"),
        "funciones": {f for (f,) in filas_sql(app, "SELECT id FROM funciones")},
    }

    # Se simula la base antigua (A/B/C y rutas viejas) y una edición hecha por el admin.
    ejecutar_sql(app, "UPDATE peliculas SET poster_url = '/posters/Viejo.jpg', clasificacion = 'A'")
    ejecutar_sql(app, "UPDATE peliculas SET genero = 'Editado por el admin' WHERE titulo = 'Moana'")

    for _ in range(2):                       # dos veces: idempotente
        with app.app_context():
            ejecutar_seed()
        assert _peliculas(app) == POSTERS_ESPERADOS

    # Nada se perdió: mismos ids y títulos, y las ventas siguen ahí.
    assert filas_sql(app, "SELECT id, titulo FROM peliculas ORDER BY id") == antes["ids"]
    assert valor_sql(app, "SELECT count(*) FROM compras") == antes["compras"]
    assert valor_sql(app, "SELECT count(*) FROM entradas") == antes["entradas"]
    assert valor_sql(app, "SELECT count(*) FROM reservas") == antes["reservas"]
    assert antes["funciones"] <= {f for (f,) in filas_sql(app, "SELECT id FROM funciones")}
    # El upsert solo toca póster y clasificación.
    assert valor_sql(app, "SELECT genero FROM peliculas WHERE titulo = 'Moana'") == "Editado por el admin"
