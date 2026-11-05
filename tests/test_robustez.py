"""Robustez ante datos de entrada hostiles (validación de TODOS los datos).

Para cada ruta que recibe cuerpo (POST/PUT) se envían cuerpos mal formados y
campos con el tipo equivocado. Ninguna combinación debe producir un error 500
(ERROR_INTERNO): siempre una respuesta controlada (2xx/4xx) con el formato
uniforme de error.
"""

import json

import pytest

CAMPOS = [
    "titulo", "genero", "clasificacion", "duracion_min", "sinopsis", "poster_url",
    "activa", "nombre", "filas", "asientos_por_fila", "pelicula_id", "sala_id",
    "inicio", "precio", "funcion_id", "asientos", "metodo_pago",
    "resultado_simulado", "cliente", "codigo", "motivo", "correo", "password",
    "rol", "documento", "contacto",
]

# Cuerpos que no son un objeto JSON, o ni siquiera son JSON.
CUERPOS_RAROS = ["[]", "[1, 2]", '"texto"', "123", "null", "true", "{", ""]

# Valores con el tipo equivocado para cada campo.
VALORES_RAROS = [123, -1, 0, 3.5, 1e308, True, None, "x", "", [1, 2], [], {"a": 1},
                 {"nombre": 5}, "a" * 5000]


def _rutas_con_cuerpo(app):
    rutas = []
    for regla in app.url_map.iter_rules():
        if not regla.rule.startswith("/api/"):
            continue
        vista = app.view_functions[regla.endpoint]
        for metodo in ("POST", "PUT"):
            if metodo in regla.methods:
                rutas.append((metodo, regla.rule, getattr(vista, "roles_permitidos", None)))
    return sorted(rutas, key=lambda r: (r[1], r[0]))


def _url(regla):
    for parametro in ("pelicula_id", "funcion_id", "sala_id", "usuario_id",
                      "reserva_id", "entrada_id"):
        regla = regla.replace(f"<int:{parametro}>", "1")
    return regla


def _cabecera(auth, permitidos):
    if permitidos is None:
        return {}                              # ruta pública
    if "administrador" in permitidos or permitidos == ():
        return auth.admin
    return auth.cliente if "cliente" in permitidos else auth.taquillero


def _problema(respuesta, descripcion):
    """Devuelve un texto describiendo el problema, o None si la respuesta es correcta."""
    if respuesta.status_code >= 500:
        return f"{descripcion} -> {respuesta.status_code}"
    if respuesta.status_code >= 400:
        cuerpo = respuesta.get_json()
        if not cuerpo or set(cuerpo) != {"error"}:
            return f"{descripcion} -> {respuesta.status_code} sin formato uniforme"
    return None


def _cuerpos_validos(esc):
    """Un cuerpo válido por ruta (método, regla, rol que la usa)."""
    a = esc.asientos
    return [
        ("POST", "/api/auth/registro", None, {
            "nombre": "Ana", "correo": "ana@x.com", "password": "secreto1",
            "documento": "1", "contacto": "300"}),
        ("POST", "/api/auth/login", None, {"correo": "cliente@prueba.com",
                                           "password": "123456"}),
        ("POST", "/api/usuarios", "admin", {
            "nombre": "Taq", "correo": "taq9@x.com", "password": "123456",
            "rol": "taquillero"}),
        ("PUT", "/api/usuarios/4", "admin", {
            "nombre": "Nuevo", "correo": "n@x.com", "rol": "cliente",
            "password": "654321", "activo": True}),
        ("POST", "/api/peliculas", "admin", {
            "titulo": "Peli", "genero": "Drama", "clasificacion": "Mayores de 12",
            "duracion_min": 90, "sinopsis": "s", "poster_url": "/p.jpg", "activa": True}),
        ("PUT", "/api/peliculas/1", "admin", {
            "titulo": "Otra", "genero": "g", "duracion_min": 100, "activa": True}),
        ("POST", "/api/salas", "admin", {"nombre": "S", "filas": 2, "asientos_por_fila": 3}),
        ("PUT", "/api/salas/1", "admin", {"nombre": "S2", "filas": 3, "asientos_por_fila": 4}),
        ("POST", "/api/funciones", "admin", {
            "pelicula_id": 1, "sala_id": 1, "inicio": "2031-01-01T20:00:00", "precio": 20000}),
        ("PUT", "/api/funciones/1", "admin", {
            "precio": 21000, "sala_id": 1, "inicio": "2031-01-01T20:00:00", "pelicula_id": 1}),
        ("POST", "/api/funciones/1/cancelar", "admin", {"motivo": "prueba"}),
        ("POST", "/api/reservas", "cliente", {"funcion_id": 1, "asientos": [a[0], a[1]]}),
        ("POST", "/api/reservas/cancelar", "cliente", {"funcion_id": 1}),
        ("POST", "/api/compras", "cliente", {
            "funcion_id": 1, "asientos": [a[2]], "metodo_pago": "tarjeta",
            "resultado_simulado": "aprobado"}),
        ("POST", "/api/compras", "taquillero", {
            "funcion_id": 1, "asientos": [a[3]], "metodo_pago": "efectivo",
            "resultado_simulado": "rechazado",
            "cliente": {"nombre": "Luis", "documento": "8", "contacto": "3"}}),
        ("POST", "/api/validaciones", "taquillero", {"codigo": "SIV-AAAAAAAAAAAA",
                                                     "funcion_id": 1}),
    ]


def test_cada_campo_con_tipo_equivocado_no_produce_500(app, http, auth, crear_escenario):
    """Parte de un cuerpo válido y altera UN campo a la vez (también los anidados)."""
    esc = crear_escenario()
    cabeceras = {None: {}, "admin": auth.admin, "cliente": auth.cliente,
                 "taquillero": auth.taquillero}
    problemas = []
    for metodo, url, rol, base in _cuerpos_validos(esc):
        cabecera = cabeceras[rol]
        rutas = [(campo, base) for campo in base]
        # Campos anidados (bloque "cliente" de la venta en taquilla).
        if isinstance(base.get("cliente"), dict):
            rutas += [(f"cliente.{k}", base) for k in base["cliente"]]
        for campo, original in rutas:
            for valor in VALORES_RAROS:
                cuerpo = json.loads(json.dumps(original))
                if "." in campo:
                    bloque, interno = campo.split(".")
                    cuerpo[bloque][interno] = valor
                else:
                    cuerpo[campo] = valor
                respuesta = http.open(url, method=metodo, headers=cabecera,
                                      data=json.dumps(cuerpo), content_type="application/json")
                problemas.append(_problema(
                    respuesta, f"{metodo} {url} {campo}={valor!r:.30}"))

    problemas = [p for p in problemas if p]
    assert not problemas, f"{len(problemas)} respuestas incorrectas:\n" + "\n".join(problemas[:40])


def test_parametros_de_consulta_hostiles_no_producen_500(app, http, auth, crear_escenario):
    """Los filtros de la URL (?desde, ?limite, ...) también se validan."""
    crear_escenario()
    parametros = ("desde", "hasta", "dias", "meses", "limite", "orden", "tipo", "rol",
                  "pelicula_id", "funcion_id", "fecha", "resultado", "todas")
    valores = ["abc", "-1", "0", "99999999999999999999999", "9999-12-31", "0000-01-01",
               "%00", "'; DROP TABLE usuarios;--", "1e9", "", "a" * 3000]
    problemas = []
    for regla in app.url_map.iter_rules():
        if not regla.rule.startswith("/api/") or "GET" not in regla.methods:
            continue
        vista = app.view_functions[regla.endpoint]
        permitidos = getattr(vista, "roles_permitidos", None)
        cabecera = _cabecera(auth, permitidos)
        url = _url(regla.rule)
        for parametro in parametros:
            for valor in valores:
                respuesta = http.get(url, headers=cabecera, query_string={parametro: valor})
                problema = _problema(respuesta, f"GET {regla.rule}?{parametro}={valor!r:.25}")
                if problema:
                    problemas.append(problema)
    assert not problemas, f"{len(problemas)} respuestas incorrectas:\n" + "\n".join(problemas[:40])


def test_hay_rutas_con_cuerpo_para_probar(app):
    assert len(_rutas_con_cuerpo(app)) >= 14


def test_ninguna_ruta_con_cuerpo_responde_500(app, http, auth, crear_escenario):
    """Cuerpos mal formados y campos de tipo equivocado nunca producen un 500."""
    crear_escenario()          # existen película 1, sala 1, función 1 y usuarios 1..4
    problemas = []
    for metodo, regla, permitidos in _rutas_con_cuerpo(app):
        cabecera = _cabecera(auth, permitidos)
        url = _url(regla)

        for crudo in CUERPOS_RAROS:
            respuesta = http.open(url, method=metodo, headers=cabecera, data=crudo,
                                  content_type="application/json")
            problemas.append(_problema(respuesta, f"{metodo} {regla} cuerpo={crudo!r}"))

        for valor in VALORES_RAROS:
            cuerpo = {campo: valor for campo in CAMPOS}
            respuesta = http.open(url, method=metodo, headers=cabecera,
                                  data=json.dumps(cuerpo), content_type="application/json")
            problemas.append(_problema(
                respuesta, f"{metodo} {regla} todos los campos={valor!r:.30}"))

    problemas = [p for p in problemas if p]
    assert not problemas, f"{len(problemas)} respuestas incorrectas:\n" + "\n".join(problemas)
