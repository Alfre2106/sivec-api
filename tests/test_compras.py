"""Compra con pago simulado y entradas (CA-07, CA-14)."""

from tests.utilidades import (
    PATRON_CODIGO, codigos_de, comprar, estado_asiento, filas_sql, reservar,
    valor_sql, vencer_reservas,
)


def test_ca07_compra_aprobada_genera_entradas_con_codigo_unico(
        app, http, auth, usuarios, crear_escenario):
    """CA-07 / RN-06: una entrada por asiento, código único con formato SIV-XXXXXXXXXXXX."""
    esc = crear_escenario(precio=20000)
    elegidos = esc.asientos[:3]
    assert reservar(http, auth.cliente, esc.funcion_id, elegidos).status_code == 201

    respuesta = comprar(http, auth.cliente, esc.funcion_id, elegidos)

    assert respuesta.status_code == 201
    cuerpo = respuesta.get_json()
    compra = cuerpo["compra"]
    assert compra["numero"] == f"C-{compra['id']:06d}"
    assert compra["total"] == 60000                       # precio * cantidad
    assert compra["estado_pago"] == "aprobado"
    assert compra["metodo_pago"] == "tarjeta"
    assert compra["funcion"]["id"] == esc.funcion_id

    codigos = codigos_de(respuesta)
    assert len(codigos) == 3 and len(set(codigos)) == 3
    assert all(PATRON_CODIGO.match(c) for c in codigos)
    assert {e["estado"] for e in cuerpo["entradas"]} == {"activa"}
    assert sorted((e["fila"], e["numero"]) for e in cuerpo["entradas"]) == [
        ("A", 1), ("A", 2), ("A", 3)]

    # Efectos en la base: asientos vendidos, reservas convertidas, cliente correcto.
    assert all(estado_asiento(app, a) == "vendido" for a in elegidos)
    assert filas_sql(app, "SELECT DISTINCT estado FROM reservas") == [("convertida",)]
    assert valor_sql(app, "SELECT cliente_id FROM compras WHERE id = :c",
                     c=compra["id"]) == usuarios.cliente.cliente_id
    assert valor_sql(app, "SELECT count(*) FROM auditoria "
                          "WHERE accion = 'compra_aprobada'") == 1


def test_ca07_compra_directa_sin_reserva_previa(app, http, auth, crear_escenario):
    """CA-07: también se puede comprar asientos disponibles sin reservarlos antes."""
    esc = crear_escenario()
    respuesta = comprar(http, auth.cliente, esc.funcion_id, esc.asientos[:2])
    assert respuesta.status_code == 201
    assert all(estado_asiento(app, a) == "vendido" for a in esc.asientos[:2])
    assert filas_sql(app, "SELECT DISTINCT estado FROM reservas") == [("convertida",)]


def test_ca07_compra_sin_lista_usa_mis_reservas(app, http, auth, crear_escenario):
    """CA-07: si se omite 'asientos', se compran todas MIS reservas activas."""
    esc = crear_escenario()
    reservar(http, auth.cliente, esc.funcion_id, esc.asientos[:2])
    reservar(http, auth.otro_cliente, esc.funcion_id, [esc.asientos[5]])

    respuesta = comprar(http, auth.cliente, esc.funcion_id)

    assert respuesta.status_code == 201
    assert len(codigos_de(respuesta)) == 2
    assert estado_asiento(app, esc.asientos[5]) == "reservado"   # la ajena no se toca
    # Sin reservas ni lista: error claro.
    sin_nada = comprar(http, auth.cliente, esc.funcion_id)
    assert sin_nada.status_code == 422
    assert sin_nada.get_json()["error"]["codigo"] == "SIN_RESERVAS"


def test_ca07_reserva_vencida_o_ajena_se_rechaza(app, http, auth, crear_escenario):
    """RN-04: reserva propia vencida => RESERVA_VENCIDA; asiento ajeno => ASIENTO_NO_DISPONIBLE."""
    esc = crear_escenario()
    propio, ajeno = esc.asientos[0], esc.asientos[1]
    reservar(http, auth.cliente, esc.funcion_id, [propio])
    reservar(http, auth.otro_cliente, esc.funcion_id, [ajeno])
    vencer_reservas(app, [propio])

    vencida = comprar(http, auth.cliente, esc.funcion_id, [propio])
    assert vencida.status_code == 409
    assert vencida.get_json()["error"]["codigo"] == "RESERVA_VENCIDA"

    de_otro = comprar(http, auth.cliente, esc.funcion_id, [ajeno])
    assert de_otro.status_code == 409
    assert de_otro.get_json()["error"]["codigo"] == "ASIENTO_NO_DISPONIBLE"
    assert valor_sql(app, "SELECT count(*) FROM compras") == 0
    assert valor_sql(app, "SELECT count(*) FROM entradas") == 0


def test_ca07_reserva_vencida_de_otro_no_bloquea_la_compra(app, http, auth, crear_escenario):
    """CA-10 / RN-03: la reserva vencida de OTRO usuario no impide comprar ese asiento."""
    esc = crear_escenario()
    asiento = esc.asientos[0]
    reservar(http, auth.otro_cliente, esc.funcion_id, [asiento])
    vencer_reservas(app, [asiento])      # el job todavía no la expiró

    respuesta = comprar(http, auth.cliente, esc.funcion_id, [asiento])

    assert respuesta.status_code == 201
    assert estado_asiento(app, asiento) == "vendido"


def test_ca07_doble_compra_de_los_mismos_asientos(app, http, auth, crear_escenario):
    """Un doble clic no duplica la compra: la segunda falla con 409."""
    esc = crear_escenario()
    assert comprar(http, auth.cliente, esc.funcion_id, esc.asientos[:2]).status_code == 201

    repetida = comprar(http, auth.cliente, esc.funcion_id, esc.asientos[:2])

    assert repetida.status_code == 409
    assert valor_sql(app, "SELECT count(*) FROM compras") == 1
    assert valor_sql(app, "SELECT count(*) FROM entradas") == 2


def test_ca07_validaciones_de_la_compra(app, http, auth, crear_escenario):
    """Método de pago por rol, cliente obligatorio en taquilla, función iniciada."""
    esc = crear_escenario()
    a = esc.asientos
    # El cliente solo paga con tarjeta; el taquillero también en efectivo.
    efectivo = comprar(http, auth.cliente, esc.funcion_id, [a[0]], metodo_pago="efectivo")
    assert efectivo.status_code == 422
    assert efectivo.get_json()["error"]["codigo"] == "METODO_PAGO_INVALIDO"
    # Taquillero: los datos del cliente son obligatorios (RN-05)...
    sin_cliente = comprar(http, auth.taquillero, esc.funcion_id, [a[0]], metodo_pago="efectivo")
    assert sin_cliente.status_code == 422
    assert sin_cliente.get_json()["error"]["codigo"] == "CLIENTE_REQUERIDO"
    # ...y con ellos la venta se registra a nombre de ese cliente sin cuenta.
    en_taquilla = comprar(http, auth.taquillero, esc.funcion_id, [a[0]],
                          metodo_pago="efectivo",
                          cliente={"nombre": "Ana Taquilla", "documento": "123"})
    assert en_taquilla.status_code == 201
    assert filas_sql(app, "SELECT nombre, usuario_id FROM clientes "
                          "WHERE nombre = 'Ana Taquilla'") == [("Ana Taquilla", None)]
    # El bloque 'cliente' se ignora para el rol cliente (usa su propia ficha).
    propia = comprar(http, auth.cliente, esc.funcion_id, [a[1]],
                     cliente={"nombre": "Suplantado"})
    assert propia.status_code == 201
    assert valor_sql(app, "SELECT count(*) FROM clientes WHERE nombre = 'Suplantado'") == 0
    # Resultado simulado inválido.
    raro = comprar(http, auth.cliente, esc.funcion_id, [a[2]], resultado="quizas")
    assert raro.status_code == 422
    # Función ya iniciada (RN-08).
    iniciada = crear_escenario(minutos=-10)
    tarde = comprar(http, auth.cliente, iniciada.funcion_id, [iniciada.asientos[0]])
    assert tarde.status_code == 409
    assert tarde.get_json()["error"]["codigo"] == "FUNCION_NO_DISPONIBLE"


def test_ca14_pago_rechazado_no_genera_entrada_y_el_asiento_sigue_reservado(
        app, http, auth, crear_escenario):
    """CA-14 / RN-13: 402 PAGO_RECHAZADO, compra rechazada guardada, sin entradas."""
    esc = crear_escenario()
    elegidos = esc.asientos[:2]
    reservar(http, auth.cliente, esc.funcion_id, elegidos)

    respuesta = comprar(http, auth.cliente, esc.funcion_id, elegidos,
                        resultado="rechazado")

    assert respuesta.status_code == 402
    error = respuesta.get_json()["error"]
    assert error["codigo"] == "PAGO_RECHAZADO"
    assert error["detalle"]["vence_en"]                       # informa hasta cuándo
    assert valor_sql(app, "SELECT count(*) FROM entradas") == 0
    assert filas_sql(app, "SELECT estado_pago FROM compras") == [("rechazado",)]
    assert all(estado_asiento(app, a) == "reservado" for a in elegidos)
    assert filas_sql(app, "SELECT DISTINCT estado FROM reservas") == [("activa",)]
    # Se puede reintentar con el mismo carrito mientras la reserva siga vigente.
    reintento = comprar(http, auth.cliente, esc.funcion_id, elegidos)
    assert reintento.status_code == 201
    assert len(codigos_de(reintento)) == 2


def test_ca14_rechazo_en_compra_directa_deja_los_asientos_reservados(
        app, http, auth, crear_escenario):
    """CA-14: aunque no hubiera reserva previa, el rechazo deja el asiento reservado hasta vencer."""
    esc = crear_escenario()
    asiento = esc.asientos[0]

    respuesta = comprar(http, auth.cliente, esc.funcion_id, [asiento],
                        resultado="rechazado")

    assert respuesta.status_code == 402
    assert respuesta.get_json()["error"]["detalle"]["vence_en"]
    assert valor_sql(app, "SELECT count(*) FROM entradas") == 0
    assert estado_asiento(app, asiento) == "reservado"
    assert filas_sql(app, "SELECT estado FROM reservas WHERE asiento_id = :a",
                     a=asiento) == [("activa",)]
    # Otra persona no puede tomarlo mientras dure esa reserva.
    ocupado = reservar(http, auth.otro_cliente, esc.funcion_id, [asiento])
    assert ocupado.status_code == 409
