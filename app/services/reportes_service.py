"""Servicio de reportes e indicadores administrativos (sección 17 de la ficha).

Todas las cifras salen de consultas SQL agregadas (GROUP BY, SUM, COUNT):
nunca se consulta fila por fila. Los servicios son de solo lectura.

DEFINICIONES (se respetan en todos los reportes)
------------------------------------------------
- ventas_totales:     suma de `compras.total` con estado_pago "aprobado" de
                      funciones NO canceladas.
- ingresos_anulados:  suma de `compras.total` aprobadas de funciones canceladas.
- entradas_vendidas:  entradas en estado "activa" o "usada" (excluye anuladas).
- entradas_anuladas:  entradas en estado "anulada".
- ocupacion:          asientos vendidos / capacidad de la sala (en %).
- Los ingresos SIEMPRE salen de `compras.total`, nunca del precio actual de la
  función (el precio puede cambiar después de vender).

FILTROS DE FECHA (?desde=YYYY-MM-DD&hasta=YYYY-MM-DD, en hora de Bogotá)
-------------------------------------------------------------------------
- Reportes de EVENTOS se filtran por la fecha del evento: compras
  (`creado_en`), reservas (`reservado_en`) e intentos de validación (`fecha`).
- Reportes POR FUNCIÓN (ventas por función, ocupación, asistencia) se filtran
  por la fecha de inicio de la función.
- Si no se envía ningún filtro, se consideran todos los datos. Si se envían
  ambos, deben cumplir desde <= hasta y no superar 2 años.
- Las series por mes agrupan en hora de Bogotá, no en UTC.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, or_

from app.extensions import db
from app.models.asiento_funcion import AsientoFuncion
from app.models.cliente import Cliente
from app.models.compra import Compra
from app.models.entrada import Entrada
from app.models.funcion import Funcion
from app.models.pelicula import Pelicula
from app.models.reserva import Reserva
from app.models.sala import Sala
from app.models.usuario import Usuario
from app.models.validacion import Validacion
from app.models.enums import (
    EstadoAsiento, EstadoEntrada, EstadoFuncion, EstadoPago, EstadoReserva,
    ResultadoValidacion,
)
from app.utils.csv_export import generar_csv
from app.utils.errores import ErrorAPI
from app.utils.tiempo import (
    ZONA_BOGOTA, a_iso_bogota, ahora_utc, parsear_dia_bogota,
)
from app.utils.validaciones import validar_entero_en_rango

# Una entrada cuenta como "vendida" si está activa o ya fue usada.
ESTADOS_VENDIDA = (EstadoEntrada.ACTIVA, EstadoEntrada.USADA)

# Máximo de días de un rango explícito (2 años).
MAX_DIAS_RANGO = 731

TIPOS_EXPORTACION = ("ventas", "ocupacion", "ranking", "validaciones")


# --- Utilidades comunes ---------------------------------------------------

def resolver_rango(desde, hasta):
    """Convierte ?desde/?hasta (YYYY-MM-DD, Bogotá) en límites UTC inclusivos.

    Devuelve (inicio_utc | None, fin_utc | None). Un límite ausente queda
    abierto. Si vienen ambos valida desde <= hasta y un máximo de 2 años.
    """
    inicio = fin = None
    if desde:
        inicio, _ = parsear_dia_bogota(desde)
    if hasta:
        _, fin = parsear_dia_bogota(hasta)

    if inicio is not None and fin is not None:
        if inicio > fin:
            raise ErrorAPI(
                "RANGO_INVALIDO",
                "La fecha 'desde' no puede ser posterior a 'hasta'.", 422)
        if (fin - inicio).days > MAX_DIAS_RANGO:
            raise ErrorAPI(
                "RANGO_MUY_AMPLIO",
                "El rango de fechas no puede superar 2 años.", 422)
    return inicio, fin


def _en_rango(columna, inicio, fin) -> list:
    """Condiciones SQL para limitar una columna de fecha al rango dado."""
    condiciones = []
    if inicio is not None:
        condiciones.append(columna >= inicio)
    if fin is not None:
        condiciones.append(columna <= fin)
    return condiciones


def _filtro_funciones(inicio, fin) -> list:
    """Funciones NO canceladas cuyo inicio cae dentro del rango."""
    return [Funcion.estado != EstadoFuncion.CANCELADA,
            *_en_rango(Funcion.inicio, inicio, fin)]


def _pct(parte, total) -> float:
    """Porcentaje con un decimal; 0.0 si el total es cero."""
    if not total:
        return 0.0
    return round(float(parte) * 100 / float(total), 1)


def _variacion(actual, anterior):
    """Variación porcentual contra el periodo anterior.

    Devuelve None si no hay datos previos (anterior = 0), porque no se puede
    calcular un cambio relativo.
    """
    if not anterior:
        return None
    return round((actual - anterior) * 100 / anterior, 1)


def _sub_vendidos(inicio, fin):
    """Subconsulta: asientos VENDIDOS por función (para ocupación)."""
    return (db.session.query(
                AsientoFuncion.funcion_id.label("funcion_id"),
                func.count(AsientoFuncion.id).label("vendidos"))
            .select_from(AsientoFuncion)
            .join(Funcion, AsientoFuncion.funcion_id == Funcion.id)
            .filter(AsientoFuncion.estado == EstadoAsiento.VENDIDO,
                    *_filtro_funciones(inicio, fin))
            .group_by(AsientoFuncion.funcion_id)
            .subquery())


# --- /resumen -------------------------------------------------------------

def _metricas_periodo(inicio, fin) -> dict:
    """Métricas de ventas, entradas y usuarios dentro de [inicio, fin]."""
    aprobada = Compra.estado_pago == EstadoPago.APROBADO

    ventas, anulados = (db.session.query(
        func.coalesce(func.sum(case(
            (Funcion.estado != EstadoFuncion.CANCELADA, Compra.total),
            else_=0)), 0),
        func.coalesce(func.sum(case(
            (Funcion.estado == EstadoFuncion.CANCELADA, Compra.total),
            else_=0)), 0))
        .select_from(Compra)
        .join(Funcion, Compra.funcion_id == Funcion.id)
        .filter(aprobada, *_en_rango(Compra.creado_en, inicio, fin))
        .one())

    vendidas, anuladas = (db.session.query(
        func.count(case((Entrada.estado.in_(ESTADOS_VENDIDA), 1))),
        func.count(case((Entrada.estado == EstadoEntrada.ANULADA, 1))))
        .select_from(Entrada)
        .join(Compra, Entrada.compra_id == Compra.id)
        .filter(aprobada, *_en_rango(Compra.creado_en, inicio, fin))
        .one())

    usuarios = (db.session.query(func.count(Usuario.id))
                .filter(*_en_rango(Usuario.creado_en, inicio, fin))
                .scalar())

    return {
        "ventas_totales": int(ventas),
        "ingresos_anulados": int(anulados),
        "entradas_vendidas": int(vendidas),
        "entradas_anuladas": int(anuladas),
        "usuarios_registrados": int(usuarios),
    }


def resumen(dias) -> dict:
    """Indicadores generales de los últimos `dias` días y su variación.

    La variación compara contra el periodo inmediatamente anterior de igual
    duración (None si no hubo datos previos).
    `funciones_activas` y `ocupacion_promedio` son una foto del momento (no
    tienen periodo anterior comparable, por eso no llevan variación).
    `ocupacion_promedio` promedia la ocupación de las funciones no canceladas
    que inician dentro del periodo o más adelante.
    """
    dias = validar_entero_en_rango(
        dias, "dias", 1, 730, codigo="DIAS_INVALIDOS")
    ahora = ahora_utc()
    inicio = ahora - timedelta(days=dias)

    actual = _metricas_periodo(inicio, ahora)
    anterior = _metricas_periodo(
        inicio - timedelta(days=dias), inicio - timedelta(microseconds=1))

    funciones_activas = (db.session.query(func.count(Funcion.id))
                         .filter(Funcion.estado == EstadoFuncion.ACTIVA,
                                 Funcion.inicio > ahora)
                         .scalar())

    vendidos = _sub_vendidos(inicio, None)
    ocupacion = (db.session.query(func.avg(
        func.coalesce(vendidos.c.vendidos, 0) * 100.0
        / func.nullif(Sala.capacidad, 0)))
        .select_from(Funcion)
        .join(Sala, Funcion.sala_id == Sala.id)
        .outerjoin(vendidos, vendidos.c.funcion_id == Funcion.id)
        .filter(*_filtro_funciones(inicio, None))
        .scalar())

    usuarios_total = db.session.query(func.count(Usuario.id)).scalar()

    return {
        "periodo": {"dias": dias, "desde": a_iso_bogota(inicio),
                    "hasta": a_iso_bogota(ahora)},
        **actual,
        "funciones_activas": int(funciones_activas),
        "ocupacion_promedio": round(float(ocupacion), 1) if ocupacion else 0.0,
        "usuarios_total": int(usuarios_total),
        "variacion": {clave: _variacion(actual[clave], anterior[clave])
                      for clave in actual},
    }


# --- /ventas-por-mes ------------------------------------------------------

def _lista_meses(cantidad: int) -> list[tuple[int, int]]:
    """Últimos `cantidad` meses (año, mes) en hora de Bogotá, del más antiguo
    al actual."""
    hoy = datetime.now(ZONA_BOGOTA)
    # Cada mes se representa como un índice (año * 12 + mes - 1) para poder
    # restar meses sin lidiar con el cambio de año.
    indice_actual = hoy.year * 12 + (hoy.month - 1)
    return [(i // 12, i % 12 + 1)
            for i in range(indice_actual - cantidad + 1, indice_actual + 1)]


def ventas_por_mes(meses) -> dict:
    """Serie mensual de ventas y entradas, con ceros en meses sin datos."""
    meses = validar_entero_en_rango(
        meses, "meses", 1, 24, codigo="MESES_INVALIDOS")
    lista = _lista_meses(meses)
    anio0, mes0 = lista[0]
    limite_inferior = datetime(anio0, mes0, 1, tzinfo=ZONA_BOGOTA).astimezone(
        timezone.utc)

    # Mes calendario en hora de Bogotá (no en UTC).
    mes_local = func.date_trunc(
        "month", func.timezone(ZONA_BOGOTA.key, Compra.creado_en))
    aprobada = Compra.estado_pago == EstadoPago.APROBADO

    ventas = dict(
        db.session.query(mes_local, func.sum(Compra.total))
        .select_from(Compra)
        .join(Funcion, Compra.funcion_id == Funcion.id)
        .filter(aprobada, Funcion.estado != EstadoFuncion.CANCELADA,
                Compra.creado_en >= limite_inferior)
        .group_by(mes_local)
        .all())
    entradas = dict(
        db.session.query(mes_local, func.count(Entrada.id))
        .select_from(Entrada)
        .join(Compra, Entrada.compra_id == Compra.id)
        .filter(aprobada, Entrada.estado.in_(ESTADOS_VENDIDA),
                Compra.creado_en >= limite_inferior)
        .group_by(mes_local)
        .all())

    # Las claves devueltas por PostgreSQL son el primer instante de cada mes.
    ventas = {(k.year, k.month): int(v) for k, v in ventas.items()}
    entradas = {(k.year, k.month): int(v) for k, v in entradas.items()}

    return {
        "meses": meses,
        "serie": [{"mes": f"{a:04d}-{m:02d}",
                   "ventas": ventas.get((a, m), 0),
                   "entradas": entradas.get((a, m), 0)}
                  for a, m in lista],
    }


# --- /ventas-por-funcion --------------------------------------------------

def ventas_por_funcion(desde, hasta) -> dict:
    """Entradas vendidas e ingresos por función (no canceladas)."""
    inicio, fin = resolver_rango(desde, hasta)
    filtro = _filtro_funciones(inicio, fin)

    ingresos = (db.session.query(
                    Compra.funcion_id.label("funcion_id"),
                    func.sum(Compra.total).label("ingresos"))
                .select_from(Compra)
                .join(Funcion, Compra.funcion_id == Funcion.id)
                .filter(Compra.estado_pago == EstadoPago.APROBADO, *filtro)
                .group_by(Compra.funcion_id)
                .subquery())
    entradas = (db.session.query(
                    Entrada.funcion_id.label("funcion_id"),
                    func.count(Entrada.id).label("cantidad"))
                .select_from(Entrada)
                .join(Funcion, Entrada.funcion_id == Funcion.id)
                .filter(Entrada.estado.in_(ESTADOS_VENDIDA), *filtro)
                .group_by(Entrada.funcion_id)
                .subquery())

    filas = (db.session.query(
                Funcion.id, Pelicula.titulo, Sala.nombre, Funcion.inicio,
                func.coalesce(entradas.c.cantidad, 0),
                func.coalesce(ingresos.c.ingresos, 0))
             .select_from(Funcion)
             .join(Pelicula, Funcion.pelicula_id == Pelicula.id)
             .join(Sala, Funcion.sala_id == Sala.id)
             .outerjoin(entradas, entradas.c.funcion_id == Funcion.id)
             .outerjoin(ingresos, ingresos.c.funcion_id == Funcion.id)
             .filter(*filtro)
             .order_by(Funcion.inicio, Funcion.id)
             .all())

    return {"funciones": [
        {"funcion_id": f[0], "pelicula": f[1], "sala": f[2],
         "inicio": a_iso_bogota(f[3]),
         "entradas_vendidas": int(f[4]), "ingresos": int(f[5])}
        for f in filas]}


# --- /ocupacion -----------------------------------------------------------

def ocupacion(desde, hasta) -> dict:
    """Ocupación por función no cancelada.

    `reservados_vigentes` cuenta reservas activas que aún no vencen.
    `porcentaje` = vendidos / capacidad.
    """
    inicio, fin = resolver_rango(desde, hasta)
    filtro = _filtro_funciones(inicio, fin)
    vendidos = _sub_vendidos(inicio, fin)

    reservados = (db.session.query(
                      AsientoFuncion.funcion_id.label("funcion_id"),
                      func.count(Reserva.id).label("reservados"))
                  .select_from(Reserva)
                  .join(AsientoFuncion, Reserva.asiento_id == AsientoFuncion.id)
                  .join(Funcion, AsientoFuncion.funcion_id == Funcion.id)
                  .filter(Reserva.estado == EstadoReserva.ACTIVA,
                          Reserva.vence_en > ahora_utc(), *filtro)
                  .group_by(AsientoFuncion.funcion_id)
                  .subquery())

    filas = (db.session.query(
                Funcion.id, Pelicula.titulo, Sala.nombre, Funcion.inicio,
                Sala.capacidad,
                func.coalesce(vendidos.c.vendidos, 0),
                func.coalesce(reservados.c.reservados, 0))
             .select_from(Funcion)
             .join(Pelicula, Funcion.pelicula_id == Pelicula.id)
             .join(Sala, Funcion.sala_id == Sala.id)
             .outerjoin(vendidos, vendidos.c.funcion_id == Funcion.id)
             .outerjoin(reservados, reservados.c.funcion_id == Funcion.id)
             .filter(*filtro)
             .order_by(Funcion.inicio, Funcion.id)
             .all())

    return {"funciones": [
        {"funcion_id": f[0], "pelicula": f[1], "sala": f[2],
         "inicio": a_iso_bogota(f[3]), "capacidad": int(f[4]),
         "vendidos": int(f[5]), "reservados_vigentes": int(f[6]),
         "porcentaje": _pct(f[5], f[4])}
        for f in filas]}


# --- /peliculas-ranking ---------------------------------------------------

def _consulta_ranking(orden, limite, inicio, fin):
    """Ranking de películas por entradas vendidas (filtrado por fecha de
    compra). Devuelve (total_entradas, filas)."""
    ventas = (db.session.query(
                  Funcion.pelicula_id.label("pelicula_id"),
                  func.count(Entrada.id).label("vendidas"))
              .select_from(Entrada)
              .join(Compra, Entrada.compra_id == Compra.id)
              .join(Funcion, Entrada.funcion_id == Funcion.id)
              .filter(Entrada.estado.in_(ESTADOS_VENDIDA),
                      *_en_rango(Compra.creado_en, inicio, fin))
              .group_by(Funcion.pelicula_id)
              .subquery())

    vendidas = func.coalesce(ventas.c.vendidas, 0)
    consulta = (db.session.query(
                    Pelicula.id, Pelicula.titulo, vendidas.label("vendidas"),
                    # Total sobre todas las filas, antes de aplicar el LIMIT.
                    func.sum(vendidas).over().label("total"))
                .select_from(Pelicula)
                .outerjoin(ventas, ventas.c.pelicula_id == Pelicula.id)
                # Una película inactiva sin ventas no aporta al ranking.
                .filter(or_(Pelicula.activa.is_(True), vendidas > 0))
                .order_by(vendidas.desc() if orden == "desc" else vendidas.asc(),
                          Pelicula.titulo))
    if limite:
        consulta = consulta.limit(limite)

    filas = consulta.all()
    total = int(filas[0].total) if filas else 0
    return total, [
        {"posicion": i, "pelicula_id": f.id, "pelicula": f.titulo,
         "entradas_vendidas": int(f.vendidas),
         "participacion": _pct(f.vendidas, total)}
        for i, f in enumerate(filas, start=1)]


def ranking_peliculas(orden, limite, desde, hasta) -> dict:
    """Ranking por entradas vendidas con % de participación sobre el total."""
    orden = (orden or "desc").strip().lower()
    if orden not in ("asc", "desc"):
        raise ErrorAPI("ORDEN_INVALIDO",
                       "El parámetro 'orden' debe ser 'asc' o 'desc'.", 422)
    limite = validar_entero_en_rango(
        limite, "limite", 1, 100, codigo="LIMITE_INVALIDO")
    inicio, fin = resolver_rango(desde, hasta)

    total, ranking = _consulta_ranking(orden, limite, inicio, fin)
    return {"orden": orden, "limite": limite, "total_entradas": total,
            "ranking": ranking}


# --- /reservas-vencidas ---------------------------------------------------

def reservas_vencidas(desde, hasta) -> dict:
    """Reservas expiradas, total de reservas y tasa de pérdida (%).

    tasa_perdida = expiradas / total de reservas del periodo.
    """
    inicio, fin = resolver_rango(desde, hasta)
    total, expiradas, convertidas, canceladas, activas = (
        db.session.query(
            func.count(Reserva.id),
            func.count(case((Reserva.estado == EstadoReserva.EXPIRADA, 1))),
            func.count(case((Reserva.estado == EstadoReserva.CONVERTIDA, 1))),
            func.count(case((Reserva.estado == EstadoReserva.CANCELADA, 1))),
            func.count(case((Reserva.estado == EstadoReserva.ACTIVA, 1))))
        .filter(*_en_rango(Reserva.reservado_en, inicio, fin))
        .one())

    return {
        "total_reservas": int(total),
        "expiradas": int(expiradas),
        "convertidas": int(convertidas),
        "canceladas": int(canceladas),
        "activas": int(activas),
        "tasa_perdida": _pct(expiradas, total),
    }


# --- /asistencia ----------------------------------------------------------

def asistencia(desde, hasta) -> dict:
    """Entradas usadas / vendidas, global y por función (no canceladas)."""
    inicio, fin = resolver_rango(desde, hasta)

    vendidas = func.count(case((Entrada.estado.in_(ESTADOS_VENDIDA), 1)))
    usadas = func.count(case((Entrada.estado == EstadoEntrada.USADA, 1)))

    filas = (db.session.query(
                Funcion.id, Pelicula.titulo, Sala.nombre, Funcion.inicio,
                vendidas, usadas)
             .select_from(Funcion)
             .join(Pelicula, Funcion.pelicula_id == Pelicula.id)
             .join(Sala, Funcion.sala_id == Sala.id)
             .join(Entrada, Entrada.funcion_id == Funcion.id)
             .filter(*_filtro_funciones(inicio, fin))
             .group_by(Funcion.id, Pelicula.titulo, Sala.nombre, Funcion.inicio)
             .having(vendidas > 0)
             .order_by(Funcion.inicio, Funcion.id)
             .all())

    total_vendidas = sum(int(f[4]) for f in filas)
    total_usadas = sum(int(f[5]) for f in filas)

    return {
        "global": {"entradas_vendidas": total_vendidas,
                   "entradas_usadas": total_usadas,
                   "porcentaje": _pct(total_usadas, total_vendidas)},
        "por_funcion": [
            {"funcion_id": f[0], "pelicula": f[1], "sala": f[2],
             "inicio": a_iso_bogota(f[3]),
             "entradas_vendidas": int(f[4]), "entradas_usadas": int(f[5]),
             "porcentaje": _pct(f[5], f[4])}
            for f in filas],
    }


# --- /intentos-rechazados -------------------------------------------------

def intentos_rechazados(desde, hasta) -> dict:
    """Conteo de validaciones rechazadas por resultado y los últimos 50."""
    inicio, fin = resolver_rango(desde, hasta)
    filtro = [Validacion.resultado != ResultadoValidacion.VALIDA,
              *_en_rango(Validacion.fecha, inicio, fin)]

    por_resultado = {r.value: 0 for r in ResultadoValidacion
                     if r != ResultadoValidacion.VALIDA}
    for resultado, cantidad in (db.session.query(
            Validacion.resultado, func.count(Validacion.id))
            .filter(*filtro).group_by(Validacion.resultado).all()):
        por_resultado[resultado.value] = int(cantidad)

    ultimos = (db.session.query(
                   Validacion.id, Validacion.fecha, Validacion.codigo_leido,
                   Validacion.resultado, Validacion.detalle, Usuario.nombre)
               .select_from(Validacion)
               .join(Usuario, Validacion.taquillero_id == Usuario.id)
               .filter(*filtro)
               .order_by(Validacion.fecha.desc(), Validacion.id.desc())
               .limit(50)
               .all())

    return {
        "total_rechazados": sum(por_resultado.values()),
        "por_resultado": por_resultado,
        "ultimos": [
            {"id": u[0], "fecha": a_iso_bogota(u[1]), "codigo_leido": u[2],
             "resultado": u[3].value, "detalle": u[4], "taquillero": u[5]}
            for u in ultimos],
    }


# --- /exportar ------------------------------------------------------------

def _filas_ventas(inicio, fin):
    """Compras aprobadas del periodo (una fila por compra)."""
    cantidad = (db.session.query(
                    Entrada.compra_id.label("compra_id"),
                    func.count(Entrada.id).label("cantidad"))
                .select_from(Entrada)
                .join(Compra, Entrada.compra_id == Compra.id)
                .filter(Compra.estado_pago == EstadoPago.APROBADO,
                        *_en_rango(Compra.creado_en, inicio, fin))
                .group_by(Entrada.compra_id)
                .subquery())

    filas = (db.session.query(
                Compra.id, Compra.creado_en, Cliente.nombre, Cliente.documento,
                Cliente.contacto, Pelicula.titulo, Sala.nombre, Funcion.inicio,
                func.coalesce(cantidad.c.cantidad, 0), Compra.total,
                Compra.metodo_pago, Usuario.nombre,
                Funcion.estado == EstadoFuncion.CANCELADA)
             .select_from(Compra)
             .join(Funcion, Compra.funcion_id == Funcion.id)
             .join(Pelicula, Funcion.pelicula_id == Pelicula.id)
             .join(Sala, Funcion.sala_id == Sala.id)
             .join(Cliente, Compra.cliente_id == Cliente.id)
             .join(Usuario, Compra.usuario_id == Usuario.id)
             .outerjoin(cantidad, cantidad.c.compra_id == Compra.id)
             .filter(Compra.estado_pago == EstadoPago.APROBADO,
                     *_en_rango(Compra.creado_en, inicio, fin))
             .order_by(Compra.creado_en, Compra.id)
             .all())

    encabezados = ["numero", "fecha", "cliente", "documento", "contacto",
                   "pelicula", "sala", "inicio_funcion", "entradas", "total",
                   "metodo_pago", "registrada_por", "funcion_cancelada"]
    return encabezados, [
        [f"C-{f[0]:06d}", a_iso_bogota(f[1]), f[2], f[3], f[4], f[5], f[6],
         a_iso_bogota(f[7]), int(f[8]), int(f[9]), f[10], f[11], bool(f[12])]
        for f in filas]


def _filas_ocupacion(desde, hasta):
    datos = ocupacion(desde, hasta)["funciones"]
    claves = ["funcion_id", "pelicula", "sala", "inicio", "capacidad",
              "vendidos", "reservados_vigentes", "porcentaje"]
    return claves, [[d[c] for c in claves] for d in datos]


def _filas_ranking(inicio, fin):
    _, ranking = _consulta_ranking("desc", None, inicio, fin)
    claves = ["posicion", "pelicula", "entradas_vendidas", "participacion"]
    return claves, [[r[c] for c in claves] for r in ranking]


def _filas_validaciones(inicio, fin):
    filas = (db.session.query(
                Validacion.id, Validacion.fecha, Validacion.codigo_leido,
                Validacion.resultado, Usuario.nombre, Validacion.detalle)
             .select_from(Validacion)
             .join(Usuario, Validacion.taquillero_id == Usuario.id)
             .filter(*_en_rango(Validacion.fecha, inicio, fin))
             .order_by(Validacion.fecha, Validacion.id)
             .all())
    encabezados = ["id", "fecha", "codigo_leido", "resultado", "taquillero",
                   "detalle"]
    return encabezados, [
        [f[0], a_iso_bogota(f[1]), f[2], f[3].value, f[4], f[5]]
        for f in filas]


def exportar_csv(tipo, desde, hasta) -> tuple[bytes, str]:
    """Genera el CSV del reporte pedido. Devuelve (contenido, nombre_archivo).

    El nombre sigue el formato sivec_<tipo>_<fecha>.csv (fecha de hoy en
    Bogotá).
    """
    tipo = (tipo or "").strip().lower()
    if tipo not in TIPOS_EXPORTACION:
        raise ErrorAPI(
            "TIPO_INVALIDO",
            "Tipo de exportación no válido. Permitidos: "
            f"{', '.join(TIPOS_EXPORTACION)}.", 422)
    inicio, fin = resolver_rango(desde, hasta)

    if tipo == "ventas":
        encabezados, filas = _filas_ventas(inicio, fin)
    elif tipo == "ocupacion":
        encabezados, filas = _filas_ocupacion(desde, hasta)
    elif tipo == "ranking":
        encabezados, filas = _filas_ranking(inicio, fin)
    else:
        encabezados, filas = _filas_validaciones(inicio, fin)

    hoy = datetime.now(ZONA_BOGOTA).strftime("%Y-%m-%d")
    return generar_csv(encabezados, filas), f"sivec_{tipo}_{hoy}.csv"
