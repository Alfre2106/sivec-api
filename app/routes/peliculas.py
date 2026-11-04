"""Blueprint de películas: consulta pública y CRUD de administrador."""

from flask import Blueprint, jsonify, request

from app.services.peliculas_service import (
    listar_peliculas_publicas, obtener_pelicula, crear_pelicula,
    editar_pelicula, desactivar_pelicula,
)
from app.utils.autorizacion import rol_requerido, id_usuario_actual
from app.utils.serializadores import serializar_pelicula
from app.utils.validaciones import obtener_cuerpo_json

bp_peliculas = Blueprint("peliculas", __name__)


@bp_peliculas.get("/peliculas")
def listar():
    """Público: lista solo las películas activas (cartelera)."""
    peliculas = listar_peliculas_publicas()
    return jsonify({
        "peliculas": [serializar_pelicula(p) for p in peliculas]
    }), 200


@bp_peliculas.get("/peliculas/<int:pelicula_id>")
def detalle(pelicula_id):
    """Público: detalle de una película activa."""
    pelicula = obtener_pelicula(pelicula_id, solo_activa=True)
    return jsonify({"pelicula": serializar_pelicula(pelicula)}), 200


@bp_peliculas.post("/peliculas")
@rol_requerido("administrador")
def crear():
    """Administrador: crea una película."""
    datos = obtener_cuerpo_json()
    pelicula = crear_pelicula(datos, admin_id=id_usuario_actual())
    return jsonify({"pelicula": serializar_pelicula(pelicula)}), 201


@bp_peliculas.put("/peliculas/<int:pelicula_id>")
@rol_requerido("administrador")
def editar(pelicula_id):
    """Administrador: edita una película."""
    datos = obtener_cuerpo_json()
    pelicula = editar_pelicula(pelicula_id, datos, admin_id=id_usuario_actual())
    return jsonify({"pelicula": serializar_pelicula(pelicula)}), 200


@bp_peliculas.delete("/peliculas/<int:pelicula_id>")
@rol_requerido("administrador")
def desactivar(pelicula_id):
    """Administrador: DELETE lógico (desactiva), nunca borra."""
    pelicula = desactivar_pelicula(pelicula_id, admin_id=id_usuario_actual())
    return jsonify({"pelicula": serializar_pelicula(pelicula)}), 200
