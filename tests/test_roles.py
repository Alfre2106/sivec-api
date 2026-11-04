"""Control de acceso por rol en TODAS las rutas (CA-12, CA-17, RNF-10).

La prueba recorre el mapa de rutas real de la aplicación (`app.url_map`, lo
mismo que lista `flask routes`) y, para cada ruta privada:
  - sin token                  -> 401
  - con un rol NO permitido    -> 403
Si alguien agrega una ruta nueva sin `@rol_requerido` y sin declararla pública
aquí, la prueba falla: así ninguna ruta privada queda sin protección.
"""

import pytest

ROLES = ("administrador", "taquillero", "cliente")

# Única lista de rutas que pueden usarse sin sesión (método, ruta).
RUTAS_PUBLICAS = {
    ("GET", "/api/salud"),
    ("POST", "/api/auth/registro"),
    ("POST", "/api/auth/login"),
    ("GET", "/api/peliculas"),
    ("GET", "/api/peliculas/<int:pelicula_id>"),
    ("GET", "/api/funciones"),
    ("GET", "/api/funciones/<int:funcion_id>"),
    ("GET", "/api/funciones/<int:funcion_id>/asientos"),
}


def _rutas_api(app):
    """Devuelve [(método, regla, función_de_vista)] de todas las rutas /api."""
    rutas = []
    for regla in app.url_map.iter_rules():
        if not regla.rule.startswith("/api/"):
            continue
        for metodo in sorted(regla.methods - {"HEAD", "OPTIONS"}):
            rutas.append((metodo, regla.rule, app.view_functions[regla.endpoint]))
    return rutas


def _url(regla):
    """Sustituye los parámetros de la ruta por un id cualquiera."""
    return (regla.replace("<int:pelicula_id>", "1").replace("<int:funcion_id>", "1")
            .replace("<int:sala_id>", "1").replace("<int:usuario_id>", "1")
            .replace("<int:reserva_id>", "1").replace("<int:entrada_id>", "1"))


def _tokens_por_rol(app):
    from flask_jwt_extended import create_access_token
    with app.app_context():
        return {rol: {"Authorization": "Bearer " + create_access_token(
            identity="1", additional_claims={"rol": rol})} for rol in ROLES}


def test_toda_ruta_es_publica_declarada_o_tiene_decorador_de_rol(app):
    """CA-12: no existe ninguna ruta que quede abierta por descuido."""
    sin_proteccion = [
        f"{metodo} {regla}" for metodo, regla, vista in _rutas_api(app)
        if not hasattr(vista, "roles_permitidos")
        and (metodo, regla) not in RUTAS_PUBLICAS]
    assert not sin_proteccion, f"Rutas sin @rol_requerido ni declaradas públicas: {sin_proteccion}"

    # Y las "públicas" declaradas realmente existen (la lista no se queda vieja).
    existentes = {(m, r) for m, r, _ in _rutas_api(app)}
    assert RUTAS_PUBLICAS <= existentes


def test_ca12_sin_token_toda_ruta_privada_responde_401(app, http):
    """CA-12: sin sesión => 401 con el formato uniforme de error."""
    privadas = [(m, r) for m, r, v in _rutas_api(app) if hasattr(v, "roles_permitidos")]
    assert len(privadas) >= 35        # protege contra recorrer una lista vacía

    for metodo, regla in privadas:
        respuesta = http.open(_url(regla), method=metodo)
        assert respuesta.status_code == 401, f"{metodo} {regla}"
        assert respuesta.get_json()["error"]["codigo"] == "TOKEN_AUSENTE", f"{metodo} {regla}"


def test_ca17_rol_incorrecto_toda_ruta_privada_responde_403(app, http):
    """CA-17: un rol no permitido => 403 en cada ruta privada."""
    tokens = _tokens_por_rol(app)
    comprobadas = 0

    for metodo, regla, vista in _rutas_api(app):
        if not hasattr(vista, "roles_permitidos"):
            continue
        permitidos = vista.roles_permitidos or ROLES        # () = cualquier autenticado
        for rol in ROLES:
            if rol in permitidos:
                continue
            respuesta = http.open(_url(regla), method=metodo, headers=tokens[rol])
            assert respuesta.status_code == 403, f"{metodo} {regla} como {rol}"
            assert respuesta.get_json()["error"]["codigo"] == "ROL_NO_AUTORIZADO"
            comprobadas += 1
    assert comprobadas >= 60


@pytest.mark.parametrize("ruta", ["/api/salud", "/api/peliculas", "/api/funciones"])
def test_las_rutas_publicas_no_piden_token(http, ruta):
    assert http.get(ruta).status_code == 200


def test_el_rol_se_toma_del_token_firmado_y_no_del_cuerpo(app, http, auth):
    """Un cliente no puede darse permisos enviando datos extra en la petición."""
    intento = http.post("/api/peliculas", headers=auth.cliente,
                        json={"titulo": "X", "rol": "administrador"})
    assert intento.status_code == 403
    sin_firma = http.get("/api/usuarios", headers={
        "Authorization": "Bearer eyJhbGciOiJub25lIn0.eyJzdWIiOiIxIiwicm9sIjoiYWRtaW5pc3RyYWRvciJ9."})
    assert sin_firma.status_code == 401
