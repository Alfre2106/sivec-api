"""Servicio de películas: consulta pública y gestión de administrador.

Las rutas delegan aquí. Las escrituras de administrador se auditan.
"""

from app.extensions import db
from app.models.pelicula import Pelicula
from app.services.auditoria_service import registrar_auditoria
from app.utils.errores import ErrorAPI
from app.utils.validaciones import validar_entero_en_rango


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


def _validar_datos_pelicula(datos: dict, exigir_titulo: bool = True) -> None:
    """Valida los campos de una película (título y duración)."""
    if exigir_titulo:
        titulo = (datos.get("titulo") or "").strip()
        if not titulo:
            raise ErrorAPI("CAMPOS_REQUERIDOS",
                           "El título es obligatorio.", 422)
    # La duración es opcional, pero si viene debe estar en rango.
    if datos.get("duracion_min") is not None:
        validar_entero_en_rango(
            datos["duracion_min"], "duracion_min", 1, 600,
            codigo="DURACION_INVALIDA")
    # poster_url debe ser texto si viene.
    if datos.get("poster_url") is not None and not isinstance(
            datos["poster_url"], str):
        raise ErrorAPI("POSTER_INVALIDO",
                       "El campo 'poster_url' debe ser texto.", 422)


def crear_pelicula(datos: dict, admin_id: int) -> Pelicula:
    """Crea una película nueva (activa por defecto)."""
    _validar_datos_pelicula(datos, exigir_titulo=True)

    pelicula = Pelicula(
        titulo=datos["titulo"].strip(),
        genero=(datos.get("genero") or None),
        clasificacion=(datos.get("clasificacion") or None),
        duracion_min=datos.get("duracion_min"),
        sinopsis=(datos.get("sinopsis") or None),
        poster_url=(datos.get("poster_url") or None),
        activa=datos.get("activa", True),
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
    _validar_datos_pelicula(datos, exigir_titulo=False)

    cambios = {}
    for campo in ("titulo", "genero", "clasificacion", "duracion_min",
                  "sinopsis", "poster_url", "activa"):
        if campo in datos and datos[campo] is not None:
            valor = datos[campo]
            if campo == "titulo":
                valor = str(valor).strip()
                if not valor:
                    continue
            setattr(pelicula, campo, valor)
            cambios[campo] = valor

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
