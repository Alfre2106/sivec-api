"""Servicio de validación de entradas en la puerta (RF-10, RF-11).

Cada intento se resuelve en UNA transacción con bloqueo de la fila de la
entrada (`with_for_update()`), de modo que dos validaciones simultáneas del
mismo código producen una 'valida' y otra 'ya_usada'. TODOS los intentos se
registran en la tabla `validaciones`.
"""

from datetime import timedelta

from flask import current_app

from app.extensions import db
from app.models.entrada import Entrada
from app.models.funcion import Funcion
from app.models.usuario import Usuario
from app.models.validacion import Validacion
from app.models.enums import EstadoEntrada, ResultadoValidacion
from app.services.auditoria_service import registrar_auditoria
from app.utils.errores import ErrorAPI
from app.utils.tiempo import ahora_utc, a_iso_bogota
from app.utils.funciones_tiempo import hora_fin


def _normalizar_codigo(codigo) -> str:
    """Normaliza el código: sin espacios y en mayúsculas."""
    if not isinstance(codigo, str) or not codigo.strip():
        raise ErrorAPI("CODIGO_REQUERIDO", "El código es obligatorio.", 422)
    return codigo.strip().upper()


def _datos_funcion(funcion: Funcion) -> dict:
    """Resumen de función para la respuesta de validación."""
    return {
        "id": funcion.id,
        "pelicula": funcion.pelicula.titulo if funcion.pelicula else None,
        "sala": funcion.sala.nombre if funcion.sala else None,
        "inicio": a_iso_bogota(funcion.inicio),
    }


def _datos_entrada(entrada: Entrada) -> dict:
    """Resumen de entrada (con asiento) para la respuesta de validación."""
    from app.models.asiento_funcion import AsientoFuncion
    asiento = db.session.get(AsientoFuncion, entrada.asiento_id)
    return {
        "id": entrada.id,
        "codigo": entrada.codigo,
        "fila": asiento.fila if asiento else None,
        "numero": asiento.numero if asiento else None,
        "estado": entrada.estado.value,
    }


def _registrar_intento(entrada_id, codigo, taquillero_id, resultado, detalle):
    """Crea el registro del intento en `validaciones` (dentro de la tx)."""
    registro = Validacion(
        entrada_id=entrada_id,
        codigo_leido=codigo,
        taquillero_id=taquillero_id,
        fecha=ahora_utc(),
        resultado=resultado,
        detalle=detalle,
    )
    db.session.add(registro)
    db.session.flush()
    return registro


def validar_entrada(datos: dict, taquillero_id: int) -> dict:
    """Valida un código de entrada. Devuelve el cuerpo de respuesta (200).

    Realiza las comprobaciones en el orden del contrato y registra SIEMPRE el
    intento. Solo la fila de la entrada se bloquea para evitar doble uso.
    """
    codigo = _normalizar_codigo(datos.get("codigo"))
    funcion_id = datos.get("funcion_id")
    if funcion_id is not None and (isinstance(funcion_id, bool)
                                   or not isinstance(funcion_id, int)):
        raise ErrorAPI("FUNCION_INVALIDA",
                       "funcion_id debe ser un entero.", 422)

    ahora = ahora_utc()

    # 1) ¿Existe el código? Bloqueamos la fila si existe.
    entrada = (Entrada.query
               .filter_by(codigo=codigo)
               .with_for_update()
               .first())

    # ---- 1. Código inexistente -> invalida ----
    if entrada is None:
        registro = _registrar_intento(
            None, codigo, taquillero_id, ResultadoValidacion.INVALIDA,
            "Código inexistente")
        db.session.commit()
        return _respuesta(
            ResultadoValidacion.INVALIDA, False,
            "La entrada no es válida.", None, None, None, registro.id)

    funcion = db.session.get(Funcion, entrada.funcion_id)

    # ---- 2. Entrada anulada (función cancelada) ----
    if entrada.estado == EstadoEntrada.ANULADA:
        registro = _registrar_intento(
            entrada.id, codigo, taquillero_id, ResultadoValidacion.ANULADA,
            "Entrada anulada")
        db.session.commit()
        return _respuesta(
            ResultadoValidacion.ANULADA, False,
            "La entrada fue anulada (función cancelada).",
            _datos_entrada(entrada), _datos_funcion(funcion), None, registro.id)

    # ---- 3. funcion_id distinto -> otra_funcion ----
    if funcion_id is not None and funcion_id != entrada.funcion_id:
        registro = _registrar_intento(
            entrada.id, codigo, taquillero_id, ResultadoValidacion.OTRA_FUNCION,
            f"Pertenece a la función {entrada.funcion_id}")
        db.session.commit()
        return _respuesta(
            ResultadoValidacion.OTRA_FUNCION, False,
            f"La entrada corresponde a la función de "
            f"{funcion.pelicula.titulo} del {a_iso_bogota(funcion.inicio)}.",
            _datos_entrada(entrada), _datos_funcion(funcion), None, registro.id)

    # ---- 4. Ya usada -> ya_usada ----
    if entrada.estado == EstadoEntrada.USADA:
        primer_uso = _info_primer_uso(entrada)
        registro = _registrar_intento(
            entrada.id, codigo, taquillero_id, ResultadoValidacion.YA_USADA,
            f"Ya usada el {a_iso_bogota(entrada.usada_en)}")
        db.session.commit()
        return _respuesta(
            ResultadoValidacion.YA_USADA, False,
            "La entrada ya fue utilizada.",
            _datos_entrada(entrada), _datos_funcion(funcion),
            primer_uso, registro.id)

    # ---- 5. Ventana horaria ----
    anticipacion = current_app.config["VALIDACION_ANTICIPACION_MINUTOS"]
    apertura = funcion.inicio - timedelta(minutes=anticipacion)
    cierre = hora_fin(funcion)
    if ahora < apertura or ahora > cierre:
        registro = _registrar_intento(
            entrada.id, codigo, taquillero_id, ResultadoValidacion.OTRA_FUNCION,
            "Fuera de la ventana horaria de la función")
        db.session.commit()
        return _respuesta(
            ResultadoValidacion.OTRA_FUNCION, False,
            f"La entrada corresponde a la función de "
            f"{funcion.pelicula.titulo} del {a_iso_bogota(funcion.inicio)}.",
            _datos_entrada(entrada), _datos_funcion(funcion), None, registro.id)

    # ---- 6. Todo bien -> valida ----
    entrada.estado = EstadoEntrada.USADA
    entrada.usada_en = ahora
    registro = _registrar_intento(
        entrada.id, codigo, taquillero_id, ResultadoValidacion.VALIDA,
        "Acceso permitido")
    registrar_auditoria(
        usuario_id=taquillero_id, accion="validar_entrada", entidad="entradas",
        entidad_id=entrada.id,
        detalle={"codigo": codigo, "funcion_id": entrada.funcion_id})
    db.session.commit()
    return _respuesta(
        ResultadoValidacion.VALIDA, True, "Acceso permitido.",
        _datos_entrada(entrada), _datos_funcion(funcion), None, registro.id)


def _info_primer_uso(entrada: Entrada) -> dict:
    """Devuelve fecha del primer uso y el taquillero que la validó.

    El primer uso se deduce de la primera validación con resultado 'valida'
    de esa entrada.
    """
    primera = (Validacion.query
               .filter_by(entrada_id=entrada.id,
                          resultado=ResultadoValidacion.VALIDA)
               .order_by(Validacion.fecha)
               .first())
    taquillero_nombre = None
    if primera:
        taq = db.session.get(Usuario, primera.taquillero_id)
        taquillero_nombre = taq.nombre if taq else None
    return {
        "fecha": a_iso_bogota(entrada.usada_en),
        "taquillero": taquillero_nombre,
    }


def _respuesta(resultado, acceso, mensaje, entrada, funcion, primer_uso,
               validacion_id) -> dict:
    """Arma el cuerpo uniforme de respuesta de una validación."""
    return {
        "resultado": resultado.value,
        "acceso_permitido": acceso,
        "mensaje": mensaje,
        "entrada": entrada,
        "funcion": funcion,
        "primer_uso": primer_uso,
        "validacion_id": validacion_id,
    }


# --- Historial ------------------------------------------------------------

def listar_validaciones(usuario_id, resultado=None, desde=None, hasta=None,
                        limite=None) -> list[dict]:
    """Historial de validaciones.

    - Taquillero: solo las suyas. Administrador: todas.
    - Filtros: resultado, rango de fechas (YYYY-MM-DD, Bogotá) y límite.
    """
    from app.utils.tiempo import parsear_dia_bogota
    usuario = db.session.get(Usuario, usuario_id)

    consulta = Validacion.query
    if usuario.rol.value == "taquillero":
        consulta = consulta.filter(Validacion.taquillero_id == usuario_id)

    if resultado:
        try:
            consulta = consulta.filter(
                Validacion.resultado == ResultadoValidacion(resultado))
        except ValueError:
            raise ErrorAPI("RESULTADO_INVALIDO",
                           "El filtro 'resultado' no es válido.", 422)
    if desde:
        inicio_utc, _ = parsear_dia_bogota(desde)
        consulta = consulta.filter(Validacion.fecha >= inicio_utc)
    if hasta:
        _, fin_utc = parsear_dia_bogota(hasta)
        consulta = consulta.filter(Validacion.fecha <= fin_utc)

    consulta = consulta.order_by(Validacion.fecha.desc())
    if limite:
        try:
            consulta = consulta.limit(int(limite))
        except (ValueError, TypeError):
            raise ErrorAPI("LIMITE_INVALIDO",
                           "El filtro 'limite' debe ser un entero.", 422)

    registros = consulta.all()
    resultado_lista = []
    for v in registros:
        taq = db.session.get(Usuario, v.taquillero_id)
        resultado_lista.append({
            "id": v.id,
            "codigo_leido": v.codigo_leido,
            "resultado": v.resultado.value,
            "fecha": a_iso_bogota(v.fecha),
            "taquillero": taq.nombre if taq else None,
            "entrada_id": v.entrada_id,
            "detalle": v.detalle,
        })
    return resultado_lista
