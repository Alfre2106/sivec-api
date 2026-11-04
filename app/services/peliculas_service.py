"""Servicio de películas: consulta pública y gestión de administrador.

Las rutas delegan aquí. Las escrituras de administrador se auditan.
"""

from app.extensions import db
from app.models.pelicula import Pelicula
from app.services.auditoria_service import registrar_auditoria
from app.utils.errores import ErrorAPI
from app.utils.validaciones import booleano, texto, validar_entero_en_rango


def listar_peliculas_publicas() -> list[Pelicula]:
    """Lista solo las películas activas (cartelera pública)."""
    return (Pelicula.query
            .filter_by(activa=True)
            .order_by(Pelicula.titulo)
            .all())


def obtener_pelicula(pelicula_id: int, solo_activa: bool = False) -> Pelicula:
    """Obtiene una película por id. Lanza 404 si no existe.

    Si `solo_activa` es True, también lanza 404 cuando está inactiva (para la
    vista pública, que no debe revelar películas desactivadas).
    """
    pelicula = db.session.get(Pelicula, pelicula_id)
    if pelicula is None or (solo_activa and not pelicula.activa):
        raise ErrorAPI("PELICULA_NO_ENCONTRADA", "La película no existe.", 404)
    return pelicula


# Longitud máxima de cada campo de texto (coincide con las columnas de la tabla).
LIMITES_TEXTO = {"genero": 80, "clasificacion": 20, "sinopsis": 5000}


def _limpiar_datos_pelicula(datos: dict, creando: bool) -> dict:
    """Valida el tipo y el rango de cada campo y devuelve solo los que vienen.

    Al crear, `titulo` es obligatorio. Al editar, los campos ausentes o nulos
    se ignoran. Lanza ErrorAPI(422) ante cualquier dato inválido.
    """
    limpio = {}

    titulo = texto(datos.get("titulo"), "titulo", obligatorio=creando, maximo=180)
    if titulo is not None:
        limpio["titulo"] = titulo

    for campo, maximo in LIMITES_TEXTO.items():
        if datos.get(campo) is not None:
            # Un texto vacío ("") vacía el campo (queda en None).
            limpio[campo] = texto(datos[campo], campo, maximo=maximo)

    # poster_url es texto (ruta o URL).
    if datos.get("poster_url") is not None:
        if not isinstance(datos["poster_url"], str):
            raise ErrorAPI("POSTER_INVALIDO",
                           "El campo 'poster_url' debe ser texto.", 422)
        limpio["poster_url"] = texto(datos["poster_url"], "poster_url", maximo=255)

    # La duración es opcional, pero si viene debe estar entre 1 y 600.
    if datos.get("duracion_min") is not None:
        limpio["duracion_min"] = validar_entero_en_rango(
            datos["duracion_min"], "duracion_min", 1, 600,
            codigo="DURACION_INVALIDA")

    if datos.get("activa") is not None:
        limpio["activa"] = booleano(datos["activa"], "activa")
    return limpio


def crear_pelicula(datos: dict, admin_id: int) -> Pelicula:
    """Crea una película nueva (activa por defecto)."""
    campos = _limpiar_datos_pelicula(datos, creando=True)

    pelicula = Pelicula(
        titulo=campos["titulo"],
        genero=campos.get("genero"),
        clasificacion=campos.get("clasificacion"),
        duracion_min=campos.get("duracion_min"),
        sinopsis=campos.get("sinopsis"),
        poster_url=campos.get("poster_url"),
        activa=campos.get("activa", True),
    )
    db.session.add(pelicula)
    db.session.flush()

    registrar_auditoria(
        usuario_id=admin_id, accion="crear_pelicula", entidad="peliculas",
        entidad_id=pelicula.id, detalle={"titulo": pelicula.titulo})
    db.session.commit()
    return pelicula


def editar_pelicula(pelicula_id: int, datos: dict, admin_id: int) -> Pelicula:
    """Edita los campos de una película existente."""
    pelicula = obtener_pelicula(pelicula_id)
    cambios = _limpiar_datos_pelicula(datos, creando=False)

    for campo, valor in cambios.items():
        setattr(pelicula, campo, valor)

    registrar_auditoria(
        usuario_id=admin_id, accion="editar_pelicula", entidad="peliculas",
        entidad_id=pelicula.id, detalle={"cambios": cambios})
    db.session.commit()
    return pelicula

def desactivar_pelicula(pelicula_id: int, admin_id: int) -> Pelicula:
    """Desactiva una película (DELETE lógico): activa=False, nunca borra."""
    pelicula = obtener_pelicula(pelicula_id)
    pelicula.activa = False

    registrar_auditoria(
        usuario_id=admin_id, accion="desactivar_pelicula", entidad="peliculas",
        entidad_id=pelicula.id, detalle={"titulo": pelicula.titulo})
    db.session.commit()
    return pelicula

