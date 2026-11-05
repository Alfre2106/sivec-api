"""Genera la colección y el entorno de Postman en docs/postman/.

Uso (desde la raíz del proyecto):
    python -m scripts.generar_postman

Se genera por código para que sea fácil mantenerla: cada request se declara una
sola vez con su cuerpo de ejemplo, sus scripts de prueba (que guardan token e ids
en el entorno) y sus ejemplos de respuesta, incluidos los errores.
"""

import json
import uuid
from pathlib import Path

DESTINO = Path(__file__).resolve().parent.parent / "docs" / "postman"
BASE = "{{base_url}}"
ESTADOS_HTTP = {200: "OK", 201: "Created", 401: "Unauthorized", 402: "Payment Required",
                403: "Forbidden", 404: "Not Found", 409: "Conflict",
                422: "Unprocessable Entity"}


# --- Construcción de requests ---------------------------------------------

def _url(ruta, consulta):
    camino = ruta.strip("/").split("/")
    url = {"raw": f"{BASE}/{ruta.strip('/')}", "host": [BASE], "path": camino}
    if consulta:
        url["query"] = [{"key": k, "value": v} for k, v in consulta.items()]
        url["raw"] += "?" + "&".join(f"{k}={v}" for k, v in consulta.items())
    return url


def R(nombre, metodo, ruta, *, cuerpo=None, consulta=None, publico=False,
      descripcion="", test=None, pre=None, ejemplos=None):
    """Declara un request.

    cuerpo:    texto JSON de ejemplo (puede usar {{variables}}).
    publico:   True = sin cabecera Authorization.
    test:      JavaScript que se ejecuta tras la respuesta (guarda ids/token).
    pre:       JavaScript previo al envío.
    ejemplos:  lista de (titulo, codigo_http, cuerpo_respuesta_dict).
    """
    solicitud = {"method": metodo, "header": [], "url": _url(ruta, consulta),
                 "description": descripcion}
    if publico:
        solicitud["auth"] = {"type": "noauth"}
    if cuerpo is not None:
        solicitud["header"].append({"key": "Content-Type", "value": "application/json"})
        solicitud["body"] = {"mode": "raw", "raw": cuerpo,
                             "options": {"raw": {"language": "json"}}}

    eventos = []
    if pre:
        eventos.append({"listen": "prerequest",
                        "script": {"type": "text/javascript", "exec": pre.strip().split("\n")}})
    if test:
        eventos.append({"listen": "test",
                        "script": {"type": "text/javascript", "exec": test.strip().split("\n")}})

    # Todo request protegido puede responder 401 sin sesión: si no tiene un
    # ejemplo de error propio, se añade ese.
    ejemplos = list(ejemplos or [])
    if not publico and not any(codigo >= 400 for _, codigo, _ in ejemplos):
        ejemplos.append(ERR_SIN_TOKEN)

    respuestas = []
    for titulo, codigo, contenido in ejemplos:
        respuestas.append({
            "name": titulo, "originalRequest": solicitud,
            "status": ESTADOS_HTTP.get(codigo, ""), "code": codigo,
            "_postman_previewlanguage": "json",
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "body": json.dumps(contenido, ensure_ascii=False, indent=2)})

    item = {"name": nombre, "request": solicitud, "response": respuestas}
    if eventos:
        item["event"] = eventos
    return item


def err(codigo, mensaje, **detalle):
    """Cuerpo de error uniforme de la API."""
    cuerpo = {"error": {"codigo": codigo, "mensaje": mensaje}}
    if detalle:
        cuerpo["error"]["detalle"] = detalle
    return cuerpo


def carpeta(nombre, descripcion, items):
    return {"name": nombre, "description": descripcion, "item": items}


def guardar(*variables):
    """JS que guarda en el entorno valores sacados de la respuesta JSON `r`."""
    return "\n".join(f'pm.environment.set("{k}", {expr});' for k, expr in variables)


def comprobar(codigo_esperado):
    return (f'pm.test("Responde {codigo_esperado}", () => '
            f'pm.response.to.have.status({codigo_esperado}));')


def _login(nombre, correo, ejemplo_rol):
    return R(
        nombre, "POST", "/auth/login", publico=True,
        cuerpo=json.dumps({"correo": correo, "password": "123456"}, indent=2),
        descripcion="Inicia sesión y guarda el token en {{token}}. Las demás peticiones de esta carpeta lo usan.",
        test=comprobar(200) + '\nconst r = pm.response.json();\n'
             + guardar(("token", "r.token")),
        ejemplos=[
            ("Éxito", 200, {"token": "eyJhbGciOiJIUzI1NiIs...", "usuario": {
                "id": 1, "nombre": ejemplo_rol, "correo": correo, "rol": ejemplo_rol.lower(),
                "activo": True, "cliente_id": None, "creado_en": "2026-11-03T21:59:01-05:00"}}),
            ("Credenciales incorrectas", 401,
             err("CREDENCIALES_INVALIDAS", "Correo o contraseña incorrectos.")),
        ])


ERR_SIN_TOKEN = ("Sin token", 401, err(
    "TOKEN_AUSENTE", "Se requiere autenticación para acceder a este recurso."))
ERR_ROL = ("Rol incorrecto", 403, err(
    "ROL_NO_AUTORIZADO", "No tienes permisos para realizar esta acción."))
FUNCION_EJEMPLO = {
    "id": 1, "pelicula": {"id": 1, "titulo": "Intensa-Mente 2", "poster_url": "/posters/intensamente-2.jpg",
                          "duracion_min": 96, "clasificacion": "Todo público", "genero": "Animación"},
    "sala": {"id": 1, "nombre": "Sala 1"}, "inicio": "2026-11-05T20:00:00-05:00",
    "fin": "2026-11-05T21:36:00-05:00", "precio": 20000, "estado": "activa",
    "capacidad": 72, "asientos_disponibles": 72}
PELICULA_EJEMPLO = {"id": 1, "titulo": "Intensa-Mente 2", "genero": "Animación", "clasificacion": "Todo público",
                    "duracion_min": 96, "sinopsis": "Las emociones de Riley.",
                    "poster_url": "/posters/intensamente-2.jpg", "activa": True}
SALA_EJEMPLO = {"id": 1, "nombre": "Sala 1", "filas": 6, "asientos_por_fila": 12, "capacidad": 72}
USUARIO_EJEMPLO = {"id": 6, "nombre": "Carlos Taquilla", "correo": "carlos@sivec.com",
                   "rol": "taquillero", "activo": True, "cliente_id": None,
                   "creado_en": "2026-11-03T21:59:04-05:00"}
ENTRADA_EJEMPLO = {"id": 1, "codigo": "SIV-ST4H2YWQ3XBS", "fila": "A", "numero": 1, "estado": "activa"}
COMPRA_EJEMPLO = {"id": 1, "numero": "C-000001", "total": 40000, "metodo_pago": "tarjeta",
                  "estado_pago": "aprobado", "creado_en": "2026-11-03T21:59:03-05:00",
                  "funcion": {"id": 1, "pelicula": "Intensa-Mente 2",
                              "inicio": "2026-11-05T20:00:00-05:00", "estado": "activa"}}
VALIDACION_BASE = {"acceso_permitido": True, "mensaje": "Acceso permitido.", "resultado": "valida",
                   "entrada": {**ENTRADA_EJEMPLO, "estado": "usada"},
                   "funcion": {"id": 1, "pelicula": "Intensa-Mente 2", "sala": "Sala 1",
                               "inicio": "2026-11-03T22:44:03-05:00"},
                   "primer_uso": None, "validacion_id": 1}
ERR_422_FECHAS = ("Rango inválido", 422, err(
    "RANGO_INVALIDO", "La fecha 'desde' no puede ser posterior a 'hasta'."))


# --- Carpetas -------------------------------------------------------------

def publico():
    return carpeta("Público", "No requieren sesión.", [
        R("Salud de la API", "GET", "/salud", publico=True,
          test=comprobar(200),
          ejemplos=[("Éxito", 200, {"estado": "ok", "servicio": "sivec-api", "base_datos": "ok",
                                    "hora_utc": "2026-11-04T02:59:01+00:00"})]),
        R("Registro de cliente", "POST", "/auth/registro", publico=True,
          cuerpo=json.dumps({"nombre": "Ana Pérez", "correo": "ana@correo.com", "password": "secreto1",
                             "documento": "1001234567", "contacto": "3001234567"},
                            indent=2, ensure_ascii=False),
          descripcion="Crea un usuario con rol cliente (siempre) y su ficha en `clientes`. Guarda el token.",
          test=comprobar(201) + '\nconst r = pm.response.json();\n' + guardar(("token", "r.token")),
          ejemplos=[
              ("Éxito", 201, {"token": "eyJhbGciOiJIUzI1NiIs...", "usuario": {
                  "id": 5, "nombre": "Ana Pérez", "correo": "ana@correo.com", "rol": "cliente",
                  "activo": True, "cliente_id": 3, "creado_en": "2026-11-03T21:59:02-05:00"}}),
              ("Correo repetido", 409, err("CORREO_YA_REGISTRADO", "El correo ya está registrado.")),
              ("Contraseña corta", 422, err("PASSWORD_CORTA",
                                            "La contraseña debe tener al menos 6 caracteres.")),
          ]),
        R("Listar películas (cartelera)", "GET", "/peliculas", publico=True,
          descripcion="Solo películas activas. Guarda `pelicula_id` de la primera.",
          test=comprobar(200) + '\nconst p = pm.response.json().peliculas;\n'
               + 'if (p.length) { pm.environment.set("pelicula_id", p[0].id); }',
          ejemplos=[("Éxito", 200, {"peliculas": [PELICULA_EJEMPLO]})]),
        R("Detalle de película", "GET", "/peliculas/{{pelicula_id}}", publico=True,
          test=comprobar(200),
          ejemplos=[("Éxito", 200, {"pelicula": PELICULA_EJEMPLO}),
                    ("No existe o está inactiva", 404,
                     err("PELICULA_NO_ENCONTRADA", "La película no existe."))]),
        R("Listar funciones (activas y futuras)", "GET", "/funciones", publico=True,
          descripcion="Solo activas, futuras y de películas activas. Guarda `funcion_id` de la primera.",
          test=comprobar(200) + '\nconst f = pm.response.json().funciones;\n'
               + 'if (f.length) { pm.environment.set("funcion_id", f[0].id); }',
          ejemplos=[("Éxito", 200, {"funciones": [FUNCION_EJEMPLO]})]),
        R("Filtrar funciones por película y día", "GET", "/funciones", publico=True,
          consulta={"pelicula_id": "{{pelicula_id}}", "fecha": "2026-11-05"},
          descripcion="`fecha` es YYYY-MM-DD en hora de Bogotá.",
          test=comprobar(200),
          ejemplos=[("Éxito", 200, {"funciones": [FUNCION_EJEMPLO]}),
                    ("Fecha inválida", 422, err("FECHA_INVALIDA",
                                                "El formato de la fecha debe ser YYYY-MM-DD."))]),
        R("Detalle de función", "GET", "/funciones/{{funcion_id}}", publico=True,
          test=comprobar(200),
          ejemplos=[("Éxito", 200, {"funcion": FUNCION_EJEMPLO}),
                    ("No existe", 404, err("FUNCION_NO_ENCONTRADA", "La función no existe."))]),
        R("Mapa de asientos (sin sesión)", "GET", "/funciones/{{funcion_id}}/asientos", publico=True,
          descripcion="Guarda `asiento_id` y `asiento_id_2` (dos asientos disponibles) para reservar y comprar.",
          test=comprobar(200) + '\nconst m = pm.response.json();\n'
               + 'const libres = m.filas.flatMap(f => f.asientos).filter(a => a.estado === "disponible");\n'
               + 'if (libres.length >= 2) {\n'
               + '  pm.environment.set("asiento_id", libres[0].id);\n'
               + '  pm.environment.set("asiento_id_2", libres[1].id);\n}',
          ejemplos=[("Éxito", 200, {
              "funcion_id": 1, "estado_funcion": "activa", "precio": 20000,
              "filas": [{"fila": "A", "asientos": [
                  {"id": 1, "numero": 1, "estado": "disponible", "mio": False},
                  {"id": 2, "numero": 2, "estado": "reservado", "mio": False}]}]})]),
    ])


def cliente():
    return carpeta("Cliente", "Ejecuta primero «Login cliente». Flujo: mapa → reservar → comprar → entradas.", [
        _login("Login cliente", "cliente@sivec.com", "Cliente"),
        R("Mi sesión (auth/yo)", "GET", "/auth/yo", test=comprobar(200),
          ejemplos=[("Éxito", 200, {"usuario": {"id": 1, "nombre": "Cliente Demo",
                                                "correo": "cliente@sivec.com", "rol": "cliente",
                                                "activo": True, "cliente_id": 1, "creado_en": "..."}}),
                    ERR_SIN_TOKEN]),
        R("Mapa de asientos (con sesión: marca «mio»)", "GET", "/funciones/{{funcion_id}}/asientos",
          descripcion="Con token, los asientos que reservaste salen con `mio: true` y `vence_en`.",
          test=comprobar(200),
          ejemplos=[("Éxito", 200, {"funcion_id": 1, "estado_funcion": "activa", "precio": 20000,
                                    "filas": [{"fila": "A", "asientos": [
                                        {"id": 1, "numero": 1, "estado": "reservado", "mio": True,
                                         "vence_en": "2026-11-03T22:04:03-05:00"}]}]})]),
        R("Reservar asientos", "POST", "/reservas",
          cuerpo='{\n  "funcion_id": {{funcion_id}},\n  "asientos": [{{asiento_id}}, {{asiento_id_2}}]\n}',
          descripcion="Todo o nada. Dura 5 minutos. Guarda `reserva_id`.",
          test=comprobar(201) + '\nconst r = pm.response.json();\n'
               + guardar(("reserva_id", "r.reservas[0].id")),
          ejemplos=[
              ("Éxito", 201, {"reservas": [{"id": 1, "asiento_id": 1, "fila": "A", "numero": 1},
                                           {"id": 2, "asiento_id": 2, "fila": "A", "numero": 2}],
                              "vence_en": "2026-11-03T22:04:03-05:00", "segundos_restantes": 299}),
              ("Asiento ya ocupado", 409, err("ASIENTO_NO_DISPONIBLE",
                                              "Uno o más asientos ya no están disponibles.",
                                              asientos_no_disponibles=[1])),
              ("Lista vacía", 422, err("ASIENTOS_REQUERIDOS", "Debes indicar al menos un asiento.")),
              ("Más de 8 asientos", 422, err("DEMASIADOS_ASIENTOS",
                                             "No puedes reservar más de 8 asientos por solicitud.")),
              ("Función cancelada o iniciada", 409, err(
                  "FUNCION_NO_DISPONIBLE",
                  "La función no está disponible para reservar (cancelada, finalizada o ya iniciada).")),
              ERR_SIN_TOKEN, ERR_ROL,
          ]),
        R("Mis reservas en una función", "GET", "/reservas/mias",
          consulta={"funcion_id": "{{funcion_id}}"}, test=comprobar(200),
          ejemplos=[("Éxito", 200, {"reservas": [{"id": 1, "asiento_id": 1, "fila": "A", "numero": 1,
                                                  "vence_en": "2026-11-03T22:04:03-05:00",
                                                  "segundos_restantes": 299}]})]),
        R("Cancelar una reserva", "DELETE", "/reservas/{{reserva_id}}", test=comprobar(200),
          ejemplos=[("Éxito", 200, {"mensaje": "Reserva cancelada."}),
                    ("Reserva de otra persona", 403, err(
                        "RESERVA_AJENA", "No puedes cancelar una reserva de otro usuario.")),
                    ("Ya no está activa", 409, err("RESERVA_NO_ACTIVA", "La reserva ya no está activa."))]),
        R("Cancelar todas mis reservas (botón Volver)", "POST", "/reservas/cancelar",
          cuerpo='{\n  "funcion_id": {{funcion_id}}\n}', test=comprobar(200),
          ejemplos=[("Éxito", 200, {"canceladas": 2})]),
        R("Comprar (pago aprobado)", "POST", "/compras",
          cuerpo='{\n  "funcion_id": {{funcion_id}},\n  "asientos": [{{asiento_id}}, {{asiento_id_2}}],\n'
                 '  "metodo_pago": "tarjeta",\n  "resultado_simulado": "aprobado"\n}',
          descripcion="Si omites `asientos`, compra todas tus reservas activas en la función. "
                      "Guarda `compra_id`, `entrada_id` y `codigo_entrada`.",
          test=comprobar(201) + '\nconst r = pm.response.json();\n'
               + guardar(("compra_id", "r.compra.id"), ("entrada_id", "r.entradas[0].id"),
                         ("codigo_entrada", "r.entradas[0].codigo")),
          ejemplos=[
              ("Éxito", 201, {"compra": COMPRA_EJEMPLO,
                              "entradas": [ENTRADA_EJEMPLO, {**ENTRADA_EJEMPLO, "id": 2, "numero": 2,
                                                             "codigo": "SIV-VWBCGVR39W25"}]}),
              ("Asientos vendidos (doble clic)", 409, err(
                  "ASIENTO_NO_DISPONIBLE", "Uno o más asientos ya no están disponibles.",
                  asientos_no_disponibles=[1, 2])),
              ("Reserva vencida", 409, err(
                  "RESERVA_VENCIDA", "Una o más reservas ya vencieron; vuelve a reservar.", asientos=[1])),
              ("Método de pago inválido", 422, err(
                  "METODO_PAGO_INVALIDO", "Método de pago no válido. Permitidos para tu rol: tarjeta.")),
              ("Sin asientos ni reservas", 422, err(
                  "SIN_RESERVAS", "No tienes reservas activas en esta función y no indicaste asientos.")),
          ]),
        R("Comprar (pago rechazado)", "POST", "/compras",
          cuerpo='{\n  "funcion_id": {{funcion_id}},\n  "asientos": [{{asiento_id}}],\n'
                 '  "metodo_pago": "tarjeta",\n  "resultado_simulado": "rechazado"\n}',
          descripcion="Responde 402: no hay entradas y los asientos siguen reservados hasta `vence_en`.",
          test='pm.test("Responde 402", () => pm.response.to.have.status(402));',
          ejemplos=[("Pago rechazado", 402, err(
              "PAGO_RECHAZADO", "El pago fue rechazado. No se generaron entradas.",
              compra_id=2, vence_en="2026-11-03T22:04:03-05:00"))]),
        R("Mis compras", "GET", "/mis-compras", test=comprobar(200),
          descripcion="Solo tus compras aprobadas, con la función y sus entradas.",
          ejemplos=[("Éxito", 200, {"compras": [{**COMPRA_EJEMPLO, "entradas": [
              {**ENTRADA_EJEMPLO, "usada_en": None}]}]}), ERR_ROL]),
        R("Detalle de mi entrada", "GET", "/entradas/{{entrada_id}}", test=comprobar(200),
          ejemplos=[("Éxito", 200, {"entrada": {**ENTRADA_EJEMPLO, "usada_en": None,
                                                "funcion_id": 1, "compra_id": 1}}),
                    ("Entrada de otra persona", 403, err(
                        "ENTRADA_AJENA", "No tienes permiso para acceder a esta entrada.")),
                    ("No existe", 404, err("ENTRADA_NO_ENCONTRADA", "La entrada no existe."))]),
        R("QR de mi entrada (imagen PNG)", "GET", "/entradas/{{entrada_id}}/qr",
          descripcion="Responde una imagen PNG. En Postman usa «Send and Download» o mírala en la vista previa.",
          test=comprobar(200) + '\npm.test("Es una imagen PNG", () => '
               'pm.expect(pm.response.headers.get("Content-Type")).to.include("image/png"));',
          ejemplos=[("Éxito (cabeceras: Content-Type: image/png)", 200,
                     {"nota": "El cuerpo es una imagen PNG binaria, no JSON."}),
                    ("Entrada de otra persona", 403, err(
                        "ENTRADA_AJENA", "No tienes permiso para acceder a esta entrada.")),
                    ("No existe", 404, err("ENTRADA_NO_ENCONTRADA", "La entrada no existe."))]),
    ])


def taquillero():
    return carpeta("Taquillero", "Ejecuta primero «Login taquillero». Venta en taquilla y validación en puerta.", [
        _login("Login taquillero", "taquillero@sivec.com", "Taquillero"),
        R("Listar salas", "GET", "/salas", test=comprobar(200) + '\nconst s = pm.response.json().salas;\n'
          + 'if (s.length) { pm.environment.set("sala_id", s[0].id); }',
          ejemplos=[("Éxito", 200, {"salas": [SALA_EJEMPLO]}), ERR_SIN_TOKEN]),
        R("Detalle de sala", "GET", "/salas/{{sala_id}}", test=comprobar(200),
          ejemplos=[("Éxito", 200, {"sala": SALA_EJEMPLO}),
                    ("No existe", 404, err("SALA_NO_ENCONTRADA", "La sala no existe."))]),
        R("Venta en taquilla (efectivo)", "POST", "/compras",
          cuerpo=json.dumps({"funcion_id": "{{funcion_id}}", "asientos": ["{{asiento_id}}"],
                             "metodo_pago": "efectivo",
                             "cliente": {"nombre": "Luis Gómez", "documento": "80123456",
                                         "contacto": "3109876543"}},
                            indent=2, ensure_ascii=False).replace('"{{', '{{').replace('}}"', '}}'),
          descripcion="Los datos del cliente son obligatorios para el taquillero (al menos `nombre`). "
                      "Guarda `entrada_id` y `codigo_entrada`.",
          test=comprobar(201) + '\nconst r = pm.response.json();\n'
               + guardar(("compra_id", "r.compra.id"), ("entrada_id", "r.entradas[0].id"),
                         ("codigo_entrada", "r.entradas[0].codigo")),
          ejemplos=[
              ("Éxito", 201, {"compra": {**COMPRA_EJEMPLO, "metodo_pago": "efectivo", "total": 20000},
                              "entradas": [ENTRADA_EJEMPLO]}),
              ("Falta el cliente", 422, err(
                  "CLIENTE_REQUERIDO",
                  "Para una venta en taquilla debes indicar los datos del cliente (al menos el nombre).")),
          ]),
        R("Venta en taquilla — función que inicia pronto (para probar «valida»)", "POST", "/compras",
          cuerpo=('{\n  "funcion_id": {{funcion_proxima_id}},\n  "asientos": [{{asiento_proximo}}],\n'
                  '  "metodo_pago": "efectivo",\n  "cliente": {"nombre": "Luis Gómez"}\n}'),
          descripcion="Requiere haber ejecutado antes «Crear función que inicia en 30 min» (carpeta Administrador). "
                      "El script previo elige un asiento libre. Guarda `codigo_entrada` para validarla.",
          pre=('pm.sendRequest({ url: pm.environment.get("base_url") + "/funciones/" + '
               'pm.environment.get("funcion_proxima_id") + "/asientos", method: "GET" }, (e, res) => {\n'
               '  const libres = res.json().filas.flatMap(f => f.asientos).filter(a => a.estado === "disponible");\n'
               '  pm.environment.set("asiento_proximo", libres[0].id);\n});'),
          test=comprobar(201) + '\nconst r = pm.response.json();\n'
               + guardar(("entrada_id", "r.entradas[0].id"), ("codigo_entrada", "r.entradas[0].codigo")),
          ejemplos=[("Éxito", 201, {"compra": COMPRA_EJEMPLO, "entradas": [ENTRADA_EJEMPLO]})]),
        R("Mis ventas (historial propio)", "GET", "/ventas",
          consulta={"desde": "2026-01-01", "hasta": "2026-12-31"}, test=comprobar(200),
          descripcion="El taquillero ve solo las ventas que registró. Filtros opcionales `desde` y `hasta`.",
          ejemplos=[("Éxito", 200, {"ventas": [{**COMPRA_EJEMPLO, "metodo_pago": "efectivo",
                                                "cliente": {"id": 4, "nombre": "Luis Gómez",
                                                            "documento": "80123456",
                                                            "contacto": "3109876543"},
                                                "entradas": [{**ENTRADA_EJEMPLO, "usada_en": None}]}]}),
                    ERR_422_FECHAS]),
        R("Validar entrada (código del entorno)", "POST", "/validaciones",
          cuerpo='{\n  "codigo": "{{codigo_entrada}}",\n  "funcion_id": {{funcion_proxima_id}}\n}',
          descripcion="Responde 200 en TODOS los resultados de negocio; revisa `resultado` y `acceso_permitido`. "
                      "Ejecútala dos veces para ver `ya_usada`.",
          test=comprobar(200) + '\nconst r = pm.response.json();\n'
               'pm.test("Hay resultado de validación", () => pm.expect(r.resultado).to.be.a("string"));',
          ejemplos=[
              ("valida", 200, VALIDACION_BASE),
              ("ya_usada", 200, {**VALIDACION_BASE, "acceso_permitido": False, "resultado": "ya_usada",
                                 "mensaje": "La entrada ya fue utilizada.", "validacion_id": 2,
                                 "primer_uso": {"fecha": "2026-11-03T21:59:03-05:00",
                                                "taquillero": "Taquillero Demo"}}),
              ("otra_funcion / fuera de horario", 200, {
                  **VALIDACION_BASE, "acceso_permitido": False, "resultado": "otra_funcion",
                  "mensaje": "La entrada corresponde a la función de Intensa-Mente 2 del 2026-11-05T20:00:00-05:00.",
                  "validacion_id": 3}),
              ("anulada", 200, {**VALIDACION_BASE, "acceso_permitido": False, "resultado": "anulada",
                                "mensaje": "La entrada fue anulada (función cancelada).", "validacion_id": 4}),
              ("Cuerpo inválido", 422, err("CODIGO_REQUERIDO", "El código es obligatorio.")),
              ERR_ROL,
          ]),
        R("Validar entrada inexistente", "POST", "/validaciones",
          cuerpo='{\n  "codigo": "SIV-NOEXISTE0000"\n}', test=comprobar(200),
          ejemplos=[("invalida", 200, {"resultado": "invalida", "acceso_permitido": False,
                                       "mensaje": "La entrada no es válida.", "entrada": None,
                                       "funcion": None, "primer_uso": None, "validacion_id": 5})]),
        R("Historial de mis validaciones", "GET", "/validaciones",
          consulta={"resultado": "valida", "limite": "10"}, test=comprobar(200),
          descripcion="El taquillero ve solo las suyas. Filtros: `resultado`, `desde`, `hasta`, `limite`.",
          ejemplos=[("Éxito", 200, {"validaciones": [{
              "id": 1, "codigo_leido": "SIV-ST4H2YWQ3XBS", "resultado": "valida",
              "fecha": "2026-11-03T21:59:03-05:00", "taquillero": "Taquillero Demo",
              "entrada_id": 1, "detalle": "Acceso permitido"}]})]),
        R("Detalle de una entrada (cualquiera)", "GET", "/entradas/{{entrada_id}}", test=comprobar(200),
          ejemplos=[("Éxito", 200, {"entrada": {**ENTRADA_EJEMPLO, "usada_en": None,
                                                "funcion_id": 1, "compra_id": 1}})]),
    ])


def administrador():
    inicio_pre = ('const d = new Date(Date.now() + %s);\n'
                  'pm.environment.set("%s", d.toISOString().slice(0, 19));')
    return carpeta("Administrador", "Ejecuta primero «Login administrador».", [
        _login("Login administrador", "admin@sivec.com", "Administrador"),

        # --- Usuarios ---
        R("Usuarios — listar (filtro por rol)", "GET", "/usuarios", consulta={"rol": "taquillero"},
          test=comprobar(200), ejemplos=[("Éxito", 200, {"usuarios": [USUARIO_EJEMPLO]}), ERR_ROL,
                                         ("Rol inválido", 422, err("ROL_INVALIDO", "Rol no válido. Valores permitidos: cliente, taquillero, administrador."))]),
        R("Usuarios — crear taquillero", "POST", "/usuarios",
          cuerpo=json.dumps({"nombre": "Carlos Taquilla", "correo": "carlos@sivec.com",
                             "password": "123456", "rol": "taquillero"}, indent=2),
          descripcion="Solo `taquillero` o `administrador`. Guarda `usuario_id`.",
          test=comprobar(201) + '\nconst r = pm.response.json();\n' + guardar(("usuario_id", "r.usuario.id")),
          ejemplos=[("Éxito", 201, {"usuario": USUARIO_EJEMPLO}),
                    ("Correo repetido", 409, err("CORREO_YA_REGISTRADO", "El correo ya está registrado.")),
                    ("Rol cliente no permitido", 422, err(
                        "ROL_NO_PERMITIDO",
                        "Por esta vía solo se pueden crear taquilleros o administradores."))]),
        R("Usuarios — editar", "PUT", "/usuarios/{{usuario_id}}",
          cuerpo='{\n  "nombre": "Carlos T. Editado"\n}', test=comprobar(200),
          ejemplos=[("Éxito", 200, {"usuario": {**USUARIO_EJEMPLO, "nombre": "Carlos T. Editado"}}),
                    ("No existe", 404, err("USUARIO_NO_ENCONTRADO", "El usuario no existe."))]),
        R("Usuarios — desactivar", "DELETE", "/usuarios/{{usuario_id}}", test=comprobar(200),
          descripcion="No borra: pone `activo = false` y el usuario ya no puede iniciar sesión.",
          ejemplos=[("Éxito", 200, {"usuario": {**USUARIO_EJEMPLO, "activo": False}})]),

        # --- Películas ---
        R("Películas — crear", "POST", "/peliculas",
          cuerpo=json.dumps({"titulo": "Moana 2", "genero": "Animación", "clasificacion": "Todo público",
                             "duracion_min": 100, "sinopsis": "Moana vuelve al océano.",
                             "poster_url": "/posters/moana.jpg"}, indent=2, ensure_ascii=False),
          descripcion="Guarda `pelicula_nueva_id`.",
          test=comprobar(201) + '\nconst r = pm.response.json();\n'
               + guardar(("pelicula_nueva_id", "r.pelicula.id")),
          ejemplos=[("Éxito", 201, {"pelicula": {**PELICULA_EJEMPLO, "id": 8, "titulo": "Moana 2"}}),
                    ("Duración inválida", 422, err(
                        "DURACION_INVALIDA", "El campo 'duracion_min' debe estar entre 1 y 600.")),
                    ("Clasificación no permitida", 422, err(
                        "CLASIFICACION_INVALIDA",
                        "La clasificación no es válida. Valores permitidos: Todo público, Mayores de 7, "
                        "Mayores de 12, Mayores de 15, Mayores de 18.")),
                    ERR_ROL]),
        R("Películas — editar", "PUT", "/peliculas/{{pelicula_nueva_id}}",
          cuerpo='{\n  "genero": "Aventura"\n}', test=comprobar(200),
          ejemplos=[("Éxito", 200, {"pelicula": {**PELICULA_EJEMPLO, "genero": "Aventura"}})]),

        # --- Salas ---
        R("Salas — crear", "POST", "/salas",
          cuerpo='{\n  "nombre": "Sala 3",\n  "filas": 6,\n  "asientos_por_fila": 10\n}',
          descripcion="`capacidad` = filas × asientos_por_fila (calculada por el servidor). Guarda `sala_nueva_id`.",
          test=comprobar(201) + '\nconst r = pm.response.json();\n' + guardar(("sala_nueva_id", "r.sala.id")),
          ejemplos=[("Éxito", 201, {"sala": {**SALA_EJEMPLO, "id": 3, "nombre": "Sala 3", "asientos_por_fila": 10,
                                             "capacidad": 60}}),
                    ("Filas fuera de rango", 422, err("FILAS_INVALIDAS",
                                                      "El campo 'filas' debe estar entre 1 y 26."))]),
        R("Salas — editar", "PUT", "/salas/{{sala_nueva_id}}", cuerpo='{\n  "nombre": "Sala 3 (VIP)"\n}',
          test=comprobar(200),
          ejemplos=[("Éxito", 200, {"sala": {**SALA_EJEMPLO, "nombre": "Sala 3 (VIP)"}}),
                    ("Distribución con funciones activas", 409, err(
                        "SALA_CON_FUNCIONES",
                        "No se puede cambiar la distribución de una sala con funciones activas."))]),

        # --- Funciones ---
        R("Funciones — crear (genera sus asientos)", "POST", "/funciones",
          cuerpo='{\n  "pelicula_id": {{pelicula_nueva_id}},\n  "sala_id": {{sala_nueva_id}},\n'
                 '  "inicio": "{{inicio_futuro}}",\n  "precio": 20000\n}',
          descripcion="`inicio` sin zona se interpreta como hora de Bogotá. Crea la función y TODOS sus asientos "
                      "en una transacción. Guarda `funcion_nueva_id`.",
          pre=inicio_pre % ("2 * 24 * 3600 * 1000", "inicio_futuro"),
          test=comprobar(201) + '\nconst r = pm.response.json();\n'
               + guardar(("funcion_nueva_id", "r.funcion.id")),
          ejemplos=[("Éxito", 201, {"funcion": FUNCION_EJEMPLO}),
                    ("Se solapa con otra", 409, err(
                        "FUNCION_SOLAPADA", "La función se solapa con la función id 1 en la misma sala.",
                        funcion_en_conflicto=1)),
                    ("Inicio en el pasado", 422, err("INICIO_NO_FUTURO", "La hora de inicio debe ser futura.")),
                    ("Película inactiva", 409, err(
                        "PELICULA_INACTIVA",
                        "No se pueden crear funciones de una película desactivada."))]),
        R("Funciones — crear una que inicia en 30 min (para validar entradas)", "POST", "/funciones",
          cuerpo='{\n  "pelicula_id": {{pelicula_nueva_id}},\n  "sala_id": {{sala_id}},\n'
                 '  "inicio": "{{inicio_proximo}}",\n  "precio": 20000\n}',
          descripcion="La validación en puerta solo acepta entradas desde 120 min antes del inicio. "
                      "Guarda `funcion_proxima_id` (si choca con otra función de la sala, cambia `sala_id`).",
          pre=inicio_pre % ("30 * 60 * 1000", "inicio_proximo"),
          test=comprobar(201) + '\nconst r = pm.response.json();\n'
               + guardar(("funcion_proxima_id", "r.funcion.id")),
          ejemplos=[("Éxito", 201, {"funcion": FUNCION_EJEMPLO})]),
        R("Funciones — editar precio", "PUT", "/funciones/{{funcion_nueva_id}}",
          cuerpo='{\n  "precio": 22000\n}',
          descripcion="Con asientos reservados o vendidos solo se puede cambiar el precio.",
          test=comprobar(200),
          ejemplos=[("Éxito", 200, {"funcion": {**FUNCION_EJEMPLO, "precio": 22000}}),
                    ("Tiene ventas", 409, err(
                        "FUNCION_CON_VENTAS",
                        "La función tiene reservas o ventas; solo se puede cambiar el precio."))]),
        R("Funciones — ver todas (incluye pasadas y canceladas)", "GET", "/funciones",
          consulta={"todas": "1"}, test=comprobar(200),
          ejemplos=[("Éxito", 200, {"funciones": [FUNCION_EJEMPLO]})]),
        R("Funciones — cancelar", "POST", "/funciones/{{funcion_nueva_id}}/cancelar",
          cuerpo='{\n  "motivo": "Falla del proyector"\n}',
          descripcion="Anula las entradas activas, libera reservas y devuelve las compras afectadas para el reembolso.",
          test=comprobar(200),
          ejemplos=[
              ("Éxito", 200, {
                  "funcion": {**FUNCION_EJEMPLO, "estado": "cancelada"}, "entradas_anuladas": 2,
                  "total_a_reembolsar": 66000,
                  "compras_afectadas": [{"compra_id": 1, "numero": "C-000001", "cantidad_entradas": 2,
                                         "total": 44000, "metodo_pago": "tarjeta",
                                         "cliente": {"nombre": "Cliente Demo", "documento": None,
                                                     "contacto": None}}]}),
              ("Ya cancelada", 409, err("FUNCION_YA_CANCELADA", "La función ya está cancelada.")),
              ("Sin motivo", 422, err("MOTIVO_REQUERIDO", "El motivo de la cancelación es obligatorio.")),
          ]),
        R("Funciones — compras afectadas (reembolso)", "GET", "/funciones/{{funcion_nueva_id}}/afectados",
          test=comprobar(200),
          ejemplos=[("Éxito", 200, {"compras_afectadas": [{
              "compra_id": 1, "numero": "C-000001", "cantidad_entradas": 2, "total": 44000,
              "metodo_pago": "tarjeta",
              "cliente": {"nombre": "Cliente Demo", "documento": None, "contacto": None}}]})]),
        R("Funciones — eliminar (solo sin ventas)", "DELETE", "/funciones/{{funcion_nueva_id}}",
          test='pm.test("200 o 409", () => pm.expect([200, 409]).to.include(pm.response.code));',
          ejemplos=[("Éxito", 200, {"mensaje": "Función eliminada."}),
                    ("Con ventas", 409, err("FUNCION_CON_VENTAS",
                                            "La función tiene ventas; use la opción de cancelar."))]),
        R("Salas — eliminar (solo sin funciones)", "DELETE", "/salas/{{sala_nueva_id}}",
          test='pm.test("200 o 409", () => pm.expect([200, 409]).to.include(pm.response.code));',
          ejemplos=[("Éxito", 200, {"mensaje": "Sala eliminada."}),
                    ("Tiene funciones", 409, err("SALA_CON_FUNCIONES",
                                                 "No se puede eliminar una sala que tiene funciones."))]),
        R("Películas — desactivar", "DELETE", "/peliculas/{{pelicula_nueva_id}}", test=comprobar(200),
          descripcion="No borra: pone `activa = false`.",
          ejemplos=[("Éxito", 200, {"pelicula": {**PELICULA_EJEMPLO, "activa": False}})]),

        # --- Ventas y validaciones ---
        R("Ventas — historial completo", "GET", "/ventas", consulta={"desde": "2026-01-01", "hasta": "2026-12-31"},
          test=comprobar(200), ejemplos=[("Éxito", 200, {"ventas": []}), ERR_422_FECHAS]),
        R("Validaciones — historial completo", "GET", "/validaciones", consulta={"limite": "50"},
          test=comprobar(200), ejemplos=[("Éxito", 200, {"validaciones": []})]),

        # --- Reportes ---
        R("Reportes — resumen", "GET", "/reportes/resumen", consulta={"dias": "30"}, test=comprobar(200),
          descripcion="`variacion` es el cambio % contra el periodo anterior (null si no hubo datos previos).",
          ejemplos=[("Éxito", 200, {
              "periodo": {"dias": 30, "desde": "2026-10-04T21:59:04-05:00", "hasta": "2026-11-03T21:59:04-05:00"},
              "ventas_totales": 120000, "ingresos_anulados": 30000, "entradas_vendidas": 6,
              "entradas_anuladas": 1, "usuarios_registrados": 6, "usuarios_total": 6,
              "funciones_activas": 2, "ocupacion_promedio": 25.0,
              "variacion": {"ventas_totales": None, "ingresos_anulados": None, "entradas_vendidas": None,
                            "entradas_anuladas": None, "usuarios_registrados": None}}),
              ("Días inválidos", 422, err("DIAS_INVALIDOS", "El campo 'dias' debe estar entre 1 y 730."))]),
        R("Reportes — ventas por mes", "GET", "/reportes/ventas-por-mes", consulta={"meses": "12"},
          test=comprobar(200),
          ejemplos=[("Éxito", 200, {"meses": 3, "serie": [{"mes": "2026-09", "ventas": 0, "entradas": 0},
                                                           {"mes": "2026-10", "ventas": 0, "entradas": 0},
                                                           {"mes": "2026-11", "ventas": 120000, "entradas": 6}]})]),
        R("Reportes — ventas por función", "GET", "/reportes/ventas-por-funcion",
          consulta={"desde": "2026-11-01", "hasta": "2026-11-30"}, test=comprobar(200),
          ejemplos=[("Éxito", 200, {"funciones": [{"funcion_id": 1, "pelicula": "Intensa-Mente 2",
                                                   "sala": "Sala 1", "inicio": "2026-11-03T22:44:03-05:00",
                                                   "entradas_vendidas": 5, "ingresos": 100000}]}),
                    ERR_422_FECHAS]),
        R("Reportes — ocupación por función", "GET", "/reportes/ocupacion", test=comprobar(200),
          ejemplos=[("Éxito", 200, {"funciones": [{"funcion_id": 1, "pelicula": "Intensa-Mente 2",
                                                   "sala": "Sala 1", "inicio": "2026-11-03T22:44:03-05:00",
                                                   "capacidad": 72, "vendidos": 5, "reservados_vigentes": 1,
                                                   "porcentaje": 6.9}]})]),
        R("Reportes — ranking de películas (más vendidas)", "GET", "/reportes/peliculas-ranking",
          consulta={"orden": "desc", "limite": "5"}, test=comprobar(200),
          descripcion="Con `orden=asc` obtienes las menos vendidas.",
          ejemplos=[("Éxito", 200, {"orden": "desc", "limite": 5, "total_entradas": 6, "ranking": [{
              "posicion": 1, "pelicula_id": 1, "pelicula": "Intensa-Mente 2",
              "entradas_vendidas": 5, "participacion": 83.3}]}),
              ("Orden inválido", 422, err("ORDEN_INVALIDO", "El parámetro 'orden' debe ser 'asc' o 'desc'."))]),
        R("Reportes — reservas vencidas", "GET", "/reportes/reservas-vencidas", test=comprobar(200),
          ejemplos=[("Éxito", 200, {"total_reservas": 9, "expiradas": 1, "convertidas": 7, "canceladas": 0,
                                    "activas": 1, "tasa_perdida": 11.1})]),
        R("Reportes — asistencia (usadas vs vendidas)", "GET", "/reportes/asistencia", test=comprobar(200),
          ejemplos=[("Éxito", 200, {"global": {"entradas_vendidas": 6, "entradas_usadas": 1, "porcentaje": 16.7},
                                    "por_funcion": []})]),
        R("Reportes — intentos de validación rechazados", "GET", "/reportes/intentos-rechazados",
          test=comprobar(200),
          ejemplos=[("Éxito", 200, {"total_rechazados": 3,
                                    "por_resultado": {"invalida": 1, "ya_usada": 1, "otra_funcion": 1,
                                                      "anulada": 0},
                                    "ultimos": [{"id": 4, "fecha": "2026-11-03T21:59:04-05:00",
                                                 "codigo_leido": "SIV-VWBCGVR39W25",
                                                 "resultado": "otra_funcion", "taquillero": "Taquillero Demo",
                                                 "detalle": "Pertenece a la función 1"}]})]),
        R("Reportes — exportar a CSV (ventas)", "GET", "/reportes/exportar",
          consulta={"tipo": "ventas", "desde": "2026-11-01", "hasta": "2026-11-30"},
          descripcion="`tipo`: ventas, ocupacion, ranking o validaciones. Devuelve un CSV (UTF-8 con BOM, separador `;`). "
                      "Usa «Send and Download» para guardarlo.",
          test=comprobar(200) + '\npm.test("Es un CSV", () => pm.expect(pm.response.headers.get("Content-Type"))'
               '.to.include("text/csv"));',
          ejemplos=[("Tipo inválido", 422, err(
              "TIPO_INVALIDO",
              "Tipo de exportación no válido. Permitidos: ventas, ocupacion, ranking, validaciones."))]),
    ])


# --- Colección y entorno --------------------------------------------------

VARIABLES = {
    "base_url": "http://localhost:5000/api", "token": "", "pelicula_id": "1", "funcion_id": "1",
    "asiento_id": "1", "asiento_id_2": "2", "reserva_id": "1", "compra_id": "1", "entrada_id": "1",
    "codigo_entrada": "", "usuario_id": "1", "sala_id": "1", "pelicula_nueva_id": "1",
    "sala_nueva_id": "1", "funcion_nueva_id": "1", "funcion_proxima_id": "1", "asiento_proximo": "1",
}

DESCRIPCION = """API REST de SIVEC (Sistema de Venta de Entradas). Documentación completa en docs/API.md.

CÓMO USARLA
1. Importa esta colección y el entorno «SIVEC Local», y selecciona el entorno (arriba a la derecha).
2. Arranca la API (python run.py) y carga los datos de prueba (flask seed).
3. Dentro de cada carpeta de rol, ejecuta primero su request «Login …»: guarda el token en {{token}}.
   Para cambiar de rol, ejecuta el login de otra carpeta.
4. Usuarios del seed (clave 123456): cliente@sivec.com, taquillero@sivec.com, admin@sivec.com.
5. Los requests guardan ids útiles en el entorno (funcion_id, asiento_id, entrada_id, codigo_entrada...).
   Puedes ejecutarlos en orden con «Run collection».

Cada request incluye un ejemplo de cuerpo y, en «Examples», ejemplos de respuesta con sus errores.
Errores: {"error": {"codigo": "...", "mensaje": "..."}}.
"""


def coleccion():
    return {
        "info": {
            "_postman_id": str(uuid.uuid4()), "name": "SIVEC API", "description": DESCRIPCION,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
        "auth": {"type": "bearer",
                 "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}]},
        "item": [publico(), cliente(), taquillero(), administrador()],
    }


def entorno():
    return {
        "id": str(uuid.uuid4()), "name": "SIVEC Local",
        "values": [{"key": k, "value": v, "type": "secret" if k == "token" else "default",
                    "enabled": True} for k, v in VARIABLES.items()],
        "_postman_variable_scope": "environment",
        "_postman_exported_using": "scripts/generar_postman.py",
    }


if __name__ == "__main__":
    DESTINO.mkdir(parents=True, exist_ok=True)
    for nombre, contenido in (("SIVEC.postman_collection.json", coleccion()),
                              ("SIVEC.postman_environment.json", entorno())):
        (DESTINO / nombre).write_text(
            json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Generado:", DESTINO / nombre)
