"""Utilidades compartidas por las pruebas (llamadas HTTP y consultas SQL)."""

import re

from sqlalchemy import text

from app.extensions import db

# Formato de código de entrada: "SIV-" + 12 caracteres sin ambiguos.
PATRON_CODIGO = re.compile(r"^SIV-[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{12}$")


def filas_sql(app, consulta, **params):
    """Ejecuta SQL y devuelve todas las filas (lista de tuplas)."""
    with app.app_context():
        return [tuple(f) for f in db.session.execute(text(consulta), params)]


def valor_sql(app, consulta, **params):
    """Ejecuta SQL y devuelve el primer valor de la primera fila."""
    with app.app_context():
        return db.session.execute(text(consulta), params).scalar()


def ejecutar_sql(app, consulta, **params):
    """Ejecuta una sentencia SQL de escritura (con commit)."""
    with app.app_context():
        db.session.execute(text(consulta), params)
        db.session.commit()


def estado_asiento(app, asiento_id):
    return valor_sql(app, "SELECT estado FROM asientos_funcion WHERE id = :i",
                     i=asiento_id)


def vencer_reservas(app, asiento_ids):
    """Simula el paso del tiempo: deja vencidas las reservas de esos asientos."""
    ejecutar_sql(
        app,
        "UPDATE reservas SET vence_en = now() - interval '1 minute' "
        "WHERE asiento_id = ANY(:ids) AND estado = 'activa'",
        ids=list(asiento_ids))


def reservar(http, cabecera, funcion_id, asientos):
    return http.post("/api/reservas", headers=cabecera,
                     json={"funcion_id": funcion_id, "asientos": list(asientos)})


def comprar(http, cabecera, funcion_id, asientos=None, metodo_pago="tarjeta",
            resultado=None, cliente=None):
    cuerpo = {"funcion_id": funcion_id, "metodo_pago": metodo_pago}
    if asientos is not None:
        cuerpo["asientos"] = list(asientos)
    if resultado:
        cuerpo["resultado_simulado"] = resultado
    if cliente:
        cuerpo["cliente"] = cliente
    return http.post("/api/compras", headers=cabecera, json=cuerpo)


def validar(http, cabecera, codigo, funcion_id=None):
    cuerpo = {"codigo": codigo}
    if funcion_id is not None:
        cuerpo["funcion_id"] = funcion_id
    return http.post("/api/validaciones", headers=cabecera, json=cuerpo)


def codigos_de(respuesta):
    """Códigos de las entradas de una respuesta de compra aprobada."""
    return [e["codigo"] for e in respuesta.get_json()["entradas"]]
