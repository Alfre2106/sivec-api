"""La colección de Postman debe coincidir con la API real (docs/postman/)."""

import json
import re
from pathlib import Path

import pytest
from werkzeug.exceptions import HTTPException

RAIZ = Path(__file__).resolve().parent.parent
COLECCION = RAIZ / "docs" / "postman" / "SIVEC.postman_collection.json"
ENTORNO = RAIZ / "docs" / "postman" / "SIVEC.postman_environment.json"
# Variables que calcula un script previo (no viven en el archivo de entorno).
DINAMICAS = {"inicio_futuro", "inicio_proximo"}


@pytest.fixture(scope="module")
def coleccion():
    assert COLECCION.exists(), "Falta la colección: python -m scripts.generar_postman"
    return json.loads(COLECCION.read_text(encoding="utf-8"))


def _requests(items, carpeta=""):
    for item in items:
        if "item" in item:
            yield from _requests(item["item"], item["name"])
        else:
            yield carpeta, item


def _ruta(item):
    """Ruta /api/... de un request, con las {{variables}} reemplazadas por 1."""
    crudo = item["request"]["url"]["raw"].split("?")[0].replace("{{base_url}}", "/api")
    return re.sub(r"\{\{[^}]+\}\}", "1", crudo)


def test_las_carpetas_son_las_pedidas(coleccion):
    assert [c["name"] for c in coleccion["item"]] == [
        "Público", "Cliente", "Taquillero", "Administrador"]


def test_todo_request_corresponde_a_una_ruta_real(app, coleccion):
    adaptador = app.url_map.bind("localhost")
    for carpeta, item in _requests(coleccion["item"]):
        metodo = item["request"]["method"]
        try:
            adaptador.match(_ruta(item), method=metodo)
        except HTTPException as error:
            pytest.fail(f"[{carpeta}] {item['name']}: {metodo} {_ruta(item)} -> {error}")


def test_la_coleccion_cubre_todos_los_endpoints(app, coleccion):
    adaptador = app.url_map.bind("localhost")
    cubiertos = set()
    for _, item in _requests(coleccion["item"]):
        regla, _ = adaptador.match(_ruta(item), method=item["request"]["method"],
                                   return_rule=True)
        cubiertos.add((item["request"]["method"], regla.rule))

    existentes = {(m, r.rule) for r in app.url_map.iter_rules()
                  if r.rule.startswith("/api/") for m in r.methods - {"HEAD", "OPTIONS"}}
    assert existentes - cubiertos == set(), "Endpoints sin request en Postman"


def test_cada_request_tiene_cuerpo_de_ejemplo_valido_y_ejemplos_de_respuesta(coleccion):
    for carpeta, item in _requests(coleccion["item"]):
        solicitud = item["request"]
        if solicitud["method"] in ("POST", "PUT") and "body" in solicitud:
            texto = re.sub(r"\{\{[^}]+\}\}", "1", solicitud["body"]["raw"])
            json.loads(texto)               # lanza error si no es JSON válido
        if solicitud["method"] in ("POST", "PUT"):
            assert "body" in solicitud or item["name"].startswith("Cancelar"), \
                f"{item['name']}: falta cuerpo de ejemplo"
        assert item["response"], f"{item['name']}: sin ejemplos de respuesta"
        for ejemplo in item["response"]:
            json.loads(ejemplo["body"])


def test_hay_ejemplos_de_error_en_los_requests_que_pueden_fallar(coleccion):
    con_error = sum(1 for _, i in _requests(coleccion["item"])
                    if any(e["code"] >= 400 for e in i["response"]))
    total = sum(1 for _ in _requests(coleccion["item"]))
    assert con_error >= total * 0.7


def test_los_logins_guardan_el_token_y_las_variables_existen_en_el_entorno(coleccion):
    entorno = json.loads(ENTORNO.read_text(encoding="utf-8"))
    nombres = {v["key"] for v in entorno["values"]} | DINAMICAS
    assert {"base_url", "token"} <= nombres

    logins = [i for _, i in _requests(coleccion["item"]) if i["name"].startswith("Login")]
    assert len(logins) == 3
    for login in logins:
        guion = "\n".join(login["event"][0]["script"]["exec"])
        assert 'pm.environment.set("token"' in guion

    texto = json.dumps(coleccion)
    usadas = set(re.findall(r"\{\{(\w+)\}\}", texto))
    asignadas = set(re.findall(r'pm\.environment\.set\(\\?"(\w+)\\?"', texto))
    assert usadas <= nombres, f"Variables sin definir en el entorno: {usadas - nombres}"
    assert asignadas <= nombres, f"Variables que se guardan pero no existen: {asignadas - nombres}"
