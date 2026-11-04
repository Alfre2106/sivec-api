"""Blueprint de reportes e indicadores (solo administrador).

Todos los endpoints son GET bajo /api/reportes/. Las rutas solo leen los
parámetros y delegan en reportes_service.
"""

from flask import Blueprint, Response, jsonify, request

from app.services import reportes_service as reportes
from app.utils.autorizacion import rol_requerido

bp_reportes = Blueprint("reportes", __name__)


def _rango():
    """Lee los filtros ?desde= y ?hasta= de la petición."""
    return request.args.get("desde"), request.args.get("hasta")


@bp_reportes.get("/reportes/resumen")
@rol_requerido("administrador")
def resumen():
    """Indicadores generales de los últimos N días (?dias=30)."""
    return jsonify(reportes.resumen(request.args.get("dias", 30))), 200


@bp_reportes.get("/reportes/ventas-por-mes")
@rol_requerido("administrador")
def ventas_por_mes():
    """Serie mensual de ventas y entradas (?meses=12)."""
    return jsonify(reportes.ventas_por_mes(request.args.get("meses", 12))), 200


@bp_reportes.get("/reportes/ventas-por-funcion")
@rol_requerido("administrador")
def ventas_por_funcion():
    """Entradas vendidas e ingresos por función."""
    return jsonify(reportes.ventas_por_funcion(*_rango())), 200


@bp_reportes.get("/reportes/ocupacion")
@rol_requerido("administrador")
def ocupacion():
    """Ocupación por función no cancelada."""
    return jsonify(reportes.ocupacion(*_rango())), 200


@bp_reportes.get("/reportes/peliculas-ranking")
@rol_requerido("administrador")
def peliculas_ranking():
    """Ranking de películas por entradas vendidas (?orden=desc|asc&limite=5)."""
    desde, hasta = _rango()
    return jsonify(reportes.ranking_peliculas(
        request.args.get("orden", "desc"), request.args.get("limite", 5),
        desde, hasta)), 200


@bp_reportes.get("/reportes/reservas-vencidas")
@rol_requerido("administrador")
def reservas_vencidas():
    """Reservas expiradas, total de reservas y tasa de pérdida."""
    return jsonify(reportes.reservas_vencidas(*_rango())), 200


@bp_reportes.get("/reportes/asistencia")
@rol_requerido("administrador")
def asistencia():
    """Entradas usadas / vendidas, global y por función."""
    return jsonify(reportes.asistencia(*_rango())), 200


@bp_reportes.get("/reportes/intentos-rechazados")
@rol_requerido("administrador")
def intentos_rechazados():
    """Conteo de validaciones rechazadas y los últimos 50 intentos."""
    return jsonify(reportes.intentos_rechazados(*_rango())), 200


@bp_reportes.get("/reportes/exportar")
@rol_requerido("administrador")
def exportar():
    """Exporta un reporte a CSV (?tipo=ventas|ocupacion|ranking|validaciones)."""
    desde, hasta = _rango()
    contenido, nombre = reportes.exportar_csv(
        request.args.get("tipo"), desde, hasta)
    return Response(
        contenido,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
