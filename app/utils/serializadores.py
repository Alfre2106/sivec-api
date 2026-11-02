"""Serializadores: convierten modelos en diccionarios listos para JSON.

Regla crítica: NUNCA incluir `password_hash` ni otros datos sensibles.
"""

from app.models.cliente import Cliente
from app.utils.funciones_tiempo import estado_efectivo, hora_fin
from app.utils.tiempo import a_iso_bogota


def serializar_usuario(usuario, incluir_cliente_id=True):
    """Serializa un usuario a dict seguro (sin password_hash).

    Si `incluir_cliente_id` es True, añade el id del cliente asociado (o None).
    """
    datos = {
        "id": usuario.id,
        "nombre": usuario.nombre,
        "correo": usuario.correo,
        "rol": usuario.rol.value,
        "activo": usuario.activo,
        "creado_en": usuario.creado_en.isoformat() if usuario.creado_en else None,
    }
    if incluir_cliente_id:
        cliente = Cliente.query.filter_by(usuario_id=usuario.id).first()
        datos["cliente_id"] = cliente.id if cliente else None
    return datos


def serializar_pelicula(pelicula) -> dict:
    """Serializa una película con todos sus campos."""
    return {
        "id": pelicula.id,
        "titulo": pelicula.titulo,
        "genero": pelicula.genero,
        "clasificacion": pelicula.clasificacion,
        "duracion_min": pelicula.duracion_min,
        "sinopsis": pelicula.sinopsis,
        "poster_url": pelicula.poster_url,
        "activa": pelicula.activa,
    }


def serializar_pelicula_resumen(pelicula) -> dict:
    """Versión reducida de la película, para anidar dentro de una función."""
    return {
        "id": pelicula.id,
        "titulo": pelicula.titulo,
        "poster_url": pelicula.poster_url,
        "duracion_min": pelicula.duracion_min,
        "clasificacion": pelicula.clasificacion,
        "genero": pelicula.genero,
    }


def serializar_sala(sala) -> dict:
    """Serializa una sala con su distribución y capacidad."""
    return {
        "id": sala.id,
        "nombre": sala.nombre,
        "filas": sala.filas,
        "asientos_por_fila": sala.asientos_por_fila,
        "capacidad": sala.capacidad,
    }


def serializar_funcion(funcion, asientos_disponibles: int | None = None) -> dict:
    """Serializa una función con su película y sala anidadas.

    `asientos_disponibles` se recibe ya calculado (consulta agregada, sin N+1).
    `estado` es el estado EFECTIVO (considera si ya finalizó por la hora).
    `fin` = inicio + duracion_min de la película.
    """
    return {
        "id": funcion.id,
        "pelicula": serializar_pelicula_resumen(funcion.pelicula),
        "sala": {"id": funcion.sala.id, "nombre": funcion.sala.nombre},
        "inicio": a_iso_bogota(funcion.inicio),
        "fin": a_iso_bogota(hora_fin(funcion)),
        "precio": funcion.precio,
        "estado": estado_efectivo(funcion).value,
        "capacidad": funcion.sala.capacidad,
        "asientos_disponibles": asientos_disponibles,
    }
