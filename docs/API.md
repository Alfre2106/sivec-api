# Referencia de la API REST de SIVEC

Documento para conectar el frontend. Los ejemplos provienen de respuestas reales de la API,
recortados o con valores adaptados para que sean legibles. La matriz de roles por endpoint está en
[ROLES.md](ROLES.md) y el modelo de datos en [MODELO_DATOS.md](MODELO_DATOS.md).

## Índice

[Convenciones](#convenciones) · [Errores comunes](#errores-comunes) ·
[Auth](#auth) · [Usuarios](#usuarios-administrador) · [Películas](#películas) ·
[Salas](#salas) · [Funciones](#funciones) · [Reservas](#reservas) ·
[Compras](#compras-y-ventas) · [Entradas](#entradas) · [Validaciones](#validaciones) ·
[Reportes](#reportes-administrador) · [Flujo típico](#flujo-típico-del-frontend)

## Convenciones

| Tema | Regla |
|---|---|
| URL base | `http://localhost:5000/api` (todas las rutas llevan el prefijo `/api`) |
| Formato | JSON (`Content-Type: application/json`), campos en `snake_case` y en español |
| Autenticación | Cabecera `Authorization: Bearer <token>` (el token lo devuelven `registro` y `login`) |
| Fechas | ISO 8601 **con zona de Bogotá**, p. ej. `2026-11-03T22:44:03-05:00`. Al enviar una fecha sin zona se interpreta como America/Bogota |
| Filtros de fecha | `YYYY-MM-DD`, interpretados en hora de Bogotá |
| Dinero | Enteros en pesos colombianos (COP), sin decimales |
| Ids | Enteros |
| Códigos HTTP | `200`/`201` éxito · `400`/`422` datos inválidos · `401` sin sesión · `402` pago rechazado · `403` rol incorrecto · `404` no existe · `409` conflicto |

**Formato uniforme de error** (en todos los endpoints):

```json
{ "error": { "codigo": "ASIENTO_NO_DISPONIBLE", "mensaje": "Uno o más asientos ya no están disponibles.",
             "detalle": { "asientos_no_disponibles": [1] } } }
```

`codigo` es estable (úsalo en el frontend para decidir qué hacer), `mensaje` está en español y
es presentable al usuario, y `detalle` aparece solo en algunos errores.

**Validación de entrada**: los cuerpos se validan siempre y nunca producen un `500`:

- Sin cuerpo, o con un JSON ilegible, se trata como vacío (verás los `CAMPOS_REQUERIDOS` del endpoint).
- Un JSON que no es un objeto (por ejemplo `[]`, `123` o `"texto"`) responde `422 CUERPO_INVALIDO`.
- Un campo con el tipo equivocado (número donde va texto, texto donde va número, etc.) responde `422 CAMPO_INVALIDO`
  (o el código específico del campo, como `PRECIO_INVALIDO`). Los textos tienen un largo máximo; si se supera,
  también `422 CAMPO_INVALIDO`.
- Los ids deben ser enteros positivos (`422 ID_INVALIDO` u otro código específico, p. ej. `ASIENTO_INVALIDO`).

Esto lo verifica la prueba automática `tests/test_robustez.py`, que altera campo por campo todos los cuerpos y filtros.

## Errores comunes

Pueden ocurrir en cualquier endpoint protegido:

| HTTP | Código | Cuándo |
|---|---|---|
| 401 | `TOKEN_AUSENTE` | No se envió la cabecera `Authorization` |
| 401 | `TOKEN_INVALIDO` | El token está mal formado o la firma no es válida |
| 401 | `TOKEN_VENCIDO` | El token expiró (`JWT_EXPIRACION_MINUTOS`, 120 por defecto); hay que iniciar sesión de nuevo |
| 403 | `ROL_NO_AUTORIZADO` | El rol del usuario no puede usar el endpoint |
| 422 | `CUERPO_INVALIDO` | El cuerpo es JSON pero no un objeto |
| 422 | `CAMPO_INVALIDO` | Un campo tiene el tipo equivocado o supera su largo máximo |
| 404 | `NOT_FOUND` | La ruta no existe (mensaje del servidor, en inglés) |
| 405 | `METHOD_NOT_ALLOWED` | Método HTTP no permitido para esa ruta (mensaje en inglés) |
| 500 | `ERROR_INTERNO` | Error inesperado del servidor |

En las tablas de cada endpoint solo se listan sus errores propios.

---

## Auth

### `GET /api/salud`
**Rol:** público. Comprueba que la API y la base de datos responden.

```json
{ "estado": "ok", "servicio": "sivec-api", "base_datos": "ok", "hora_utc": "2026-11-04T02:59:01+00:00" }
```
Si la base no responde devuelve `503` con `"estado": "degradado"` y `"base_datos": "error"`.

### `POST /api/auth/registro`
**Rol:** público. Crea un usuario con rol `cliente` **siempre** (cualquier `rol` enviado se ignora)
y su ficha en `clientes`. Devuelve ya la sesión iniciada.

Cuerpo (`documento` y `contacto` opcionales; `password` mínimo 6 caracteres; el correo se
normaliza a minúsculas y sin espacios):
```json
{ "nombre": "Ana Pérez", "correo": "ana@correo.com", "password": "secreto1",
  "documento": "1001234567", "contacto": "3001234567" }
```

**201**:
```json
{ "token": "eyJhbGciOiJIUzI1NiIs...",
  "usuario": { "id": 5, "nombre": "Ana Pérez", "correo": "ana@correo.com", "rol": "cliente",
               "activo": true, "cliente_id": 3, "creado_en": "2026-11-03T21:59:02-05:00" } }
```

| HTTP | Código | Cuándo |
|---|---|---|
| 409 | `CORREO_YA_REGISTRADO` | El correo ya existe |
| 422 | `CAMPOS_REQUERIDOS` | Falta `nombre`, `correo` o `password` |
| 422 | `CORREO_INVALIDO` | Formato de correo inválido |
| 422 | `PASSWORD_CORTA` | Menos de 6 caracteres |
| 422 | `PASSWORD_LARGA` | Más de 72 caracteres (límite de bcrypt) |

### `POST /api/auth/login`
**Rol:** público.
```json
{ "correo": "cliente@sivec.com", "password": "123456" }
```
**200**: igual que el registro (`token` + `usuario`). `usuario.cliente_id` es `null` para
taquilleros y administradores. El token incluye el rol y vence a los `JWT_EXPIRACION_MINUTOS`.

| HTTP | Código | Cuándo |
|---|---|---|
| 401 | `CREDENCIALES_INVALIDAS` | Correo inexistente **o** clave incorrecta (mismo mensaje: "Correo o contraseña incorrectos.") |
| 401 | `USUARIO_INACTIVO` | La cuenta fue desactivada |
| 422 | `CAMPOS_REQUERIDOS` | Falta `correo` o `password` |

### `GET /api/auth/yo`
**Rol:** cualquier usuario autenticado. **200**: `{ "usuario": { ...mismos campos que login } }`.

---

## Usuarios (administrador)

Taquilleros y administradores **solo** se crean aquí. Ninguna respuesta incluye `password_hash`.

### `GET /api/usuarios`
**Rol:** administrador. Filtro opcional `?rol=cliente|taquillero|administrador`.
**200**: `{ "usuarios": [ { "id": 2, "nombre": "...", "correo": "...", "rol": "taquillero", "activo": true, "cliente_id": null, "creado_en": "..." } ] }`

| HTTP | Código | Cuándo |
|---|---|---|
| 422 | `ROL_INVALIDO` | `rol` no es uno de los tres valores |

### `POST /api/usuarios`
**Rol:** administrador. Solo `taquillero` o `administrador`.
```json
{ "nombre": "Carlos Taquilla", "correo": "carlos@sivec.com", "password": "123456", "rol": "taquillero" }
```
**201**: `{ "usuario": { "id": 6, "nombre": "Carlos Taquilla", "correo": "carlos@sivec.com", "rol": "taquillero", "activo": true, "cliente_id": null, "creado_en": "..." } }`

| HTTP | Código | Cuándo |
|---|---|---|
| 409 | `CORREO_YA_REGISTRADO` | Correo repetido |
| 422 | `CAMPOS_REQUERIDOS` | Falta `nombre`, `correo`, `password` o `rol` |
| 422 | `CORREO_INVALIDO` · `PASSWORD_CORTA` | Formato o longitud |
| 422 | `ROL_INVALIDO` | Rol desconocido |
| 422 | `ROL_NO_PERMITIDO` | Se pidió `cliente` (los clientes se registran por `/auth/registro`) |

### `PUT /api/usuarios/{id}`
**Rol:** administrador. Edición parcial; todos los campos son opcionales:
`nombre`, `correo`, `rol`, `password`, `activo`.
```json
{ "nombre": "Nombre Nuevo" }
```
**200**: `{ "usuario": { ... } }`. Errores: `404 USUARIO_NO_ENCONTRADO`, `409 CORREO_YA_REGISTRADO`,
`422` (`CORREO_INVALIDO`, `PASSWORD_CORTA`, `ROL_INVALIDO`).

### `DELETE /api/usuarios/{id}`
**Rol:** administrador. **Desactiva** (no borra): `activo` pasa a `false` y el usuario ya no puede
iniciar sesión. **200**: `{ "usuario": { ..., "activo": false } }`. Error: `404 USUARIO_NO_ENCONTRADO`.

---

## Películas

Objeto película: `{ id, titulo, genero, clasificacion, duracion_min, sinopsis, poster_url, activa }`.

### `GET /api/peliculas`
**Rol:** público. Solo las películas **activas**, ordenadas por título.
```json
{ "peliculas": [ { "id": 1, "titulo": "Intensa-Mente 2", "genero": "Animación", "clasificacion": "A",
                   "duracion_min": 96, "sinopsis": "Las emociones de Riley.",
                   "poster_url": "/posters/intensa-mente-2.jpg", "activa": true } ] }
```

### `GET /api/peliculas/{id}`
**Rol:** público. **200**: `{ "pelicula": { ... } }`. Una película inactiva responde `404 PELICULA_NO_ENCONTRADA`.

### `POST /api/peliculas`
**Rol:** administrador. Solo `titulo` es obligatorio; `duracion_min` entre 1 y 600; `poster_url` es
texto (ruta o URL); `activa` es opcional (por defecto `true`).
```json
{ "titulo": "Intensa-Mente 2", "genero": "Animación", "clasificacion": "A", "duracion_min": 96,
  "sinopsis": "Las emociones de Riley.", "poster_url": "/posters/intensa-mente-2.jpg" }
```
**201**: `{ "pelicula": { ... } }`

| HTTP | Código | Cuándo |
|---|---|---|
| 422 | `CAMPOS_REQUERIDOS` | Falta `titulo` |
| 422 | `DURACION_INVALIDA` | `duracion_min` fuera de 1–600 o no entero |
| 422 | `POSTER_INVALIDO` | `poster_url` no es texto |

### `PUT /api/peliculas/{id}`
**Rol:** administrador. Edición parcial (mismos campos). **200**: `{ "pelicula": { ... } }`.
Errores: `404 PELICULA_NO_ENCONTRADA`, `422 DURACION_INVALIDA`, `422 POSTER_INVALIDO`.

### `DELETE /api/peliculas/{id}`
**Rol:** administrador. **Solo desactiva** (`activa = false`), nunca borra. Una película inactiva
sale de la cartelera, no admite funciones nuevas y sus funciones dejan de listarse públicamente.
**200**: `{ "pelicula": { ..., "activa": false } }`. Error: `404 PELICULA_NO_ENCONTRADA`.

---

## Salas

Objeto sala: `{ id, nombre, filas, asientos_por_fila, capacidad }` con
`capacidad = filas × asientos_por_fila` (calculada por el servidor).

### `GET /api/salas` · `GET /api/salas/{id}`
**Rol:** administrador, taquillero. **200**: `{ "salas": [ ... ] }` / `{ "sala": { ... } }`.
Error: `404 SALA_NO_ENCONTRADA`.
```json
{ "sala": { "id": 1, "nombre": "Sala 1", "filas": 6, "asientos_por_fila": 12, "capacidad": 72 } }
```

### `POST /api/salas`
**Rol:** administrador. `filas` de 1 a 26 (letras A–Z), `asientos_por_fila` de 1 a 30.
```json
{ "nombre": "Sala 1", "filas": 6, "asientos_por_fila": 12 }
```
**201**: `{ "sala": { ... } }`

| HTTP | Código | Cuándo |
|---|---|---|
| 422 | `CAMPOS_REQUERIDOS` | Falta `nombre` |
| 422 | `FILAS_INVALIDAS` | `filas` fuera de 1–26 o no entero |
| 422 | `ASIENTOS_INVALIDOS` | `asientos_por_fila` fuera de 1–30 o no entero |

### `PUT /api/salas/{id}`
**Rol:** administrador. Edición parcial (`nombre`, `filas`, `asientos_por_fila`); recalcula `capacidad`.
Errores: `404 SALA_NO_ENCONTRADA`, `422` (los de arriba), y
`409 SALA_CON_FUNCIONES` si se intenta cambiar `filas` o `asientos_por_fila` con funciones **activas**
(desajustaría los mapas de asientos). Cambiar solo el `nombre` siempre se permite.

### `DELETE /api/salas/{id}`
**Rol:** administrador. Borra la sala **solo si no tiene ninguna función**. **200**: `{ "mensaje": "Sala eliminada." }`.
Errores: `404 SALA_NO_ENCONTRADA`, `409 SALA_CON_FUNCIONES`.

---

## Funciones

Objeto función:

```json
{ "id": 1,
  "pelicula": { "id": 1, "titulo": "Intensa-Mente 2", "poster_url": "/posters/intensa-mente-2.jpg",
                "duracion_min": 96, "clasificacion": "A", "genero": "Animación" },
  "sala": { "id": 1, "nombre": "Sala Principal" },
  "inicio": "2026-11-03T22:44:03-05:00", "fin": "2026-11-04T00:20:03-05:00",
  "precio": 20000, "estado": "activa", "capacidad": 72, "asientos_disponibles": 72 }
```

- `fin` = `inicio` + `duracion_min` de la película.
- `estado` es el **efectivo**: `activa`, `cancelada` o `finalizada` (una función activa cuya hora de fin ya pasó).
- `asientos_disponibles` cuenta los asientos en estado `disponible`.

### `GET /api/funciones`
**Rol:** público. Solo funciones `activa`, **futuras** (no iniciadas) y de películas activas, ordenadas por `inicio`.
Filtros opcionales: `?pelicula_id=1` y `?fecha=2026-11-03` (día en hora de Bogotá).
Un administrador (con token) puede añadir `?todas=1` para ver también pasadas, canceladas y de películas
inactivas; para cualquier otro, `todas` se ignora.
**200**: `{ "funciones": [ { ... } ] }`. Error: `422 FECHA_INVALIDA`.

### `GET /api/funciones/{id}`
**Rol:** público. Incluye funciones ya iniciadas, para mostrar su detalle con su `estado`.
**200**: `{ "funcion": { ... } }`. Error: `404 FUNCION_NO_ENCONTRADA`.

### `GET /api/funciones/{id}/asientos`
**Rol:** público; el token es **opcional**. Si se envía y es válido, marca con `mio: true` (y `vence_en`)
los asientos que ese usuario tiene reservados.

```json
{ "funcion_id": 1, "estado_funcion": "activa", "precio": 22000,
  "filas": [
    { "fila": "A", "asientos": [
        { "id": 1, "numero": 1, "estado": "reservado", "mio": true, "vence_en": "2026-11-03T22:04:03-05:00" },
        { "id": 2, "numero": 2, "estado": "disponible", "mio": false } ] },
    { "fila": "B", "asientos": [ { "id": 13, "numero": 1, "estado": "disponible", "mio": false } ] } ] }
```

- `estado`: `disponible`, `reservado` o `vendido`.
- Una reserva que ya venció se muestra como `disponible` aunque el job aún no la haya liberado.
- `vence_en` solo aparece en los asientos con `mio: true`.

Error: `404 FUNCION_NO_ENCONTRADA`.

### `POST /api/funciones`
**Rol:** administrador. En **una sola transacción** crea la función y **todos** sus asientos
(filas A, B, C… × números 1..N) en `disponible`. Si algo falla, no queda nada creado.
```json
{ "pelicula_id": 1, "sala_id": 1, "inicio": "2026-11-05T20:00:00", "precio": 20000 }
```
`inicio` en ISO 8601 (sin zona = hora de Bogotá, se guarda en UTC). **201**: `{ "funcion": { ... } }`

| HTTP | Código | Cuándo |
|---|---|---|
| 404 | `PELICULA_NO_ENCONTRADA` · `SALA_NO_ENCONTRADA` | No existen |
| 409 | `PELICULA_INACTIVA` | La película está desactivada |
| 409 | `FUNCION_SOLAPADA` | Choca con otra función de la sala (duración + 15 min de margen). `detalle.funcion_en_conflicto` indica cuál |
| 422 | `CAMPOS_REQUERIDOS` | Falta `pelicula_id` o `sala_id` |
| 422 | `FECHA_INVALIDA` · `INICIO_NO_FUTURO` | Formato de fecha inválido / `inicio` no es futuro |
| 422 | `PRECIO_INVALIDO` | `precio` no es un entero entre 1 y 1.000.000 (COP por entrada) |

### `PUT /api/funciones/{id}`
**Rol:** administrador. Campos opcionales: `precio`, `sala_id`, `inicio`, `pelicula_id`.
No se edita una función cancelada o ya iniciada. Si ya tiene asientos reservados o vendidos,
**solo** se puede cambiar el `precio`.
```json
{ "precio": 22000 }
```
**200**: `{ "funcion": { ... } }`

| HTTP | Código | Cuándo |
|---|---|---|
| 404 | `FUNCION_NO_ENCONTRADA` | No existe |
| 409 | `FUNCION_CANCELADA` · `FUNCION_YA_INICIADA` | No es editable |
| 409 | `FUNCION_CON_VENTAS` | Se intentó cambiar sala, inicio o película con reservas/ventas |
| 409 | `FUNCION_SOLAPADA` · `PELICULA_INACTIVA` | Igual que al crear |
| 422 | `PRECIO_INVALIDO` · `INICIO_NO_FUTURO` · `FECHA_INVALIDA` | Datos inválidos |

### `DELETE /api/funciones/{id}`
**Rol:** administrador. Borra la función y sus asientos **solo si no tiene compras, entradas ni reservas**.
**200**: `{ "mensaje": "Función eliminada." }`

| HTTP | Código | Cuándo |
|---|---|---|
| 404 | `FUNCION_NO_ENCONTRADA` | No existe |
| 409 | `FUNCION_CON_VENTAS` | "La función tiene ventas; use la opción de cancelar." |

### `POST /api/funciones/{id}/cancelar`
**Rol:** administrador. En una transacción (con bloqueo de la fila de la función): la función pasa a
`cancelada`; las entradas **activas** pasan a `anulada` (las ya usadas no se tocan); las reservas
activas se cancelan y sus asientos vuelven a `disponible`. El motivo queda en la auditoría.
```json
{ "motivo": "Falla del proyector" }
```
**200**:
```json
{ "funcion": { "id": 1, "estado": "cancelada", "...": "..." },
  "entradas_anuladas": 2, "total_a_reembolsar": 66000,
  "compras_afectadas": [
    { "compra_id": 1, "numero": "C-000001", "cantidad_entradas": 2, "total": 44000, "metodo_pago": "tarjeta",
      "cliente": { "nombre": "Cliente Prueba", "documento": null, "contacto": null } },
    { "compra_id": 3, "numero": "C-000003", "cantidad_entradas": 1, "total": 22000, "metodo_pago": "efectivo",
      "cliente": { "nombre": "Luis Gómez", "documento": "80123456", "contacto": "3109876543" } } ] }
```

| HTTP | Código | Cuándo |
|---|---|---|
| 404 | `FUNCION_NO_ENCONTRADA` | No existe |
| 409 | `FUNCION_YA_CANCELADA` | Ya estaba cancelada |
| 409 | `FUNCION_FINALIZADA` | Ya terminó |
| 422 | `MOTIVO_REQUERIDO` | Falta `motivo` |

### `GET /api/funciones/{id}/afectados`
**Rol:** administrador. La misma lista `compras_afectadas` (compras aprobadas de la función), consultable
también después de cancelar. **200**: `{ "compras_afectadas": [ ... ] }`. Error: `404 FUNCION_NO_ENCONTRADA`.

---

## Reservas

Una reserva dura `RESERVA_DURACION_MINUTOS` (5 por defecto). Al vencer, el asiento vuelve a `disponible`.
Límites configurables: 8 asientos por solicitud y 8 reservas activas por usuario y función.

### `POST /api/reservas`
**Rol:** cliente, taquillero. **Todo o nada**: si algún asiento no está disponible no se reserva ninguno.
```json
{ "funcion_id": 1, "asientos": [1, 2] }
```
`asientos` son los `id` de asiento que devuelve el mapa. **201**:
```json
{ "reservas": [ { "id": 1, "asiento_id": 1, "fila": "A", "numero": 1 },
                { "id": 2, "asiento_id": 2, "fila": "A", "numero": 2 } ],
  "vence_en": "2026-11-03T22:04:03-05:00", "segundos_restantes": 299 }
```
Usa `segundos_restantes` (o `vence_en`) para el temporizador del carrito.

| HTTP | Código | Cuándo |
|---|---|---|
| 404 | `FUNCION_NO_ENCONTRADA` | La función no existe |
| 409 | `FUNCION_NO_DISPONIBLE` | Cancelada, finalizada o ya iniciada (RN-08) |
| 409 | `ASIENTO_NO_DISPONIBLE` | `detalle.asientos_no_disponibles` lista los ids ocupados |
| 409 | `LIMITE_RESERVAS` | Supera las reservas activas permitidas en la función (`detalle`: `activas`, `maximo`) |
| 422 | `FUNCION_REQUERIDA` | Falta `funcion_id` o no es entero |
| 422 | `ASIENTOS_REQUERIDOS` · `ASIENTOS_REPETIDOS` · `ASIENTO_INVALIDO` | Lista vacía, con repetidos, ids no enteros, o ids inexistentes / de otra función |
| 422 | `DEMASIADOS_ASIENTOS` | Más de 8 asientos |

### `GET /api/reservas/mias?funcion_id={id}`
**Rol:** cliente, taquillero. Mis reservas **activas y vigentes** en esa función.
```json
{ "reservas": [ { "id": 1, "asiento_id": 1, "fila": "A", "numero": 1,
                  "vence_en": "2026-11-03T22:04:03-05:00", "segundos_restantes": 299 } ] }
```
Error: `422 FUNCION_REQUERIDA`.

### `DELETE /api/reservas/{id}`
**Rol:** cliente, taquillero. Solo el dueño y solo si está activa; el asiento vuelve a `disponible`.
**200**: `{ "mensaje": "Reserva cancelada." }`

| HTTP | Código | Cuándo |
|---|---|---|
| 403 | `RESERVA_AJENA` | Es de otro usuario |
| 404 | `RESERVA_NO_ENCONTRADA` | No existe |
| 409 | `RESERVA_NO_ACTIVA` | Ya fue cancelada, expiró o se convirtió en compra |

### `POST /api/reservas/cancelar`
**Rol:** cliente, taquillero. Cancela **todas** mis reservas activas en una función (botón "Volver").
```json
{ "funcion_id": 1 }
```
**200**: `{ "canceladas": 2 }`. Error: `422 FUNCION_REQUERIDA`.

---

## Compras y ventas

El pago es **simulado** (`resultado_simulado`).

### `POST /api/compras`
**Rol:** cliente, taquillero. En una transacción con bloqueo de filas: valida función, cliente y asientos;
los asientos libres se reservan primero y luego se vende. Una compra con asientos que ya reservaste se
completa omitiendo `asientos` (usa todas **mis** reservas activas en esa función).

```json
{ "funcion_id": 1, "asientos": [1, 2], "metodo_pago": "tarjeta", "resultado_simulado": "aprobado" }
```

| Campo | Detalle |
|---|---|
| `funcion_id` | Obligatorio |
| `asientos` | Opcional. Si se omite se usan todas mis reservas activas en la función |
| `metodo_pago` | Cliente: `tarjeta`. Taquillero: `tarjeta` o `efectivo` |
| `resultado_simulado` | `aprobado` (por defecto) o `rechazado` |
| `cliente` | `{ nombre, documento, contacto }`. **Obligatorio (al menos `nombre`) para el taquillero**; se ignora para el rol cliente, que usa su propia ficha |

Venta en taquilla:
```json
{ "funcion_id": 1, "asientos": [21], "metodo_pago": "efectivo",
  "cliente": { "nombre": "Luis Gómez", "documento": "80123456", "contacto": "3109876543" } }
```

**201 (aprobado)**: asientos → `vendido`, reservas → `convertida`, una entrada por asiento.
```json
{ "compra": { "id": 1, "numero": "C-000001", "total": 44000, "metodo_pago": "tarjeta",
              "estado_pago": "aprobado", "creado_en": "2026-11-03T21:59:03-05:00",
              "funcion": { "id": 1, "pelicula": "Intensa-Mente 2", "inicio": "2026-11-03T22:44:03-05:00", "estado": "activa" } },
  "entradas": [ { "id": 1, "codigo": "SIV-ST4H2YWQ3XBS", "fila": "A", "numero": 1, "estado": "activa" },
                { "id": 2, "codigo": "SIV-VWBCGVR39W25", "fila": "A", "numero": 2, "estado": "activa" } ] }
```
`total` = precio de la función × cantidad. `numero` = `C-` + id con 6 dígitos.

**402 (rechazado)**: se guarda la compra con `estado_pago = rechazado`, **no** hay entradas y los asientos
quedan **reservados** hasta `vence_en`, por lo que se puede reintentar el pago.
```json
{ "error": { "codigo": "PAGO_RECHAZADO", "mensaje": "El pago fue rechazado. No se generaron entradas.",
             "detalle": { "compra_id": 2, "vence_en": "2026-11-03T22:04:03-05:00" } } }
```

| HTTP | Código | Cuándo |
|---|---|---|
| 402 | `PAGO_RECHAZADO` | `resultado_simulado = rechazado` |
| 404 | `FUNCION_NO_ENCONTRADA` | La función no existe |
| 409 | `FUNCION_NO_DISPONIBLE` | Cancelada, finalizada o iniciada (RN-08) |
| 409 | `RESERVA_VENCIDA` | Una reserva **tuya** ya venció (`detalle.asientos`) |
| 409 | `ASIENTO_NO_DISPONIBLE` | Vendido o reservado por otra persona. Un doble clic recibe este error en la segunda solicitud |
| 422 | `FUNCION_REQUERIDA` | Falta `funcion_id` |
| 422 | `METODO_PAGO_INVALIDO` | Método no permitido para el rol |
| 422 | `RESULTADO_INVALIDO` | `resultado_simulado` distinto de `aprobado`/`rechazado` |
| 422 | `CLIENTE_REQUERIDO` | Taquillero sin `cliente.nombre` |
| 422 | `CLIENTE_INVALIDO` | `cliente` no es un objeto |
| 422 | `SIN_RESERVAS` | Sin `asientos` y sin reservas activas |
| 422 | `ASIENTOS_REQUERIDOS` · `ASIENTOS_REPETIDOS` · `ASIENTO_INVALIDO` | Lista inválida o asientos de otra función |

### `GET /api/mis-compras`
**Rol:** cliente. **Solo** sus compras **aprobadas** (nunca las de otro usuario), más recientes primero,
con la función (incluido su `estado`: si se canceló verás `cancelada`) y sus entradas
(`estado`: `activa`, `usada` o `anulada`).
```json
{ "compras": [ { "id": 1, "numero": "C-000001", "total": 44000, "metodo_pago": "tarjeta",
                 "estado_pago": "aprobado", "creado_en": "2026-11-03T21:59:03-05:00",
                 "funcion": { "id": 1, "pelicula": "Intensa-Mente 2", "inicio": "2026-11-03T22:44:03-05:00", "estado": "activa" },
                 "entradas": [ { "id": 1, "codigo": "SIV-ST4H2YWQ3XBS", "fila": "A", "numero": 1,
                                 "estado": "activa", "usada_en": null } ] } ] }
```

### `GET /api/ventas`
**Rol:** taquillero, administrador. El taquillero ve **solo las que registró**; el administrador, todas.
Filtros opcionales `?desde=YYYY-MM-DD&hasta=YYYY-MM-DD`. Cada venta añade el `cliente`:
```json
{ "ventas": [ { "id": 3, "numero": "C-000003", "total": 22000, "metodo_pago": "efectivo", "estado_pago": "aprobado",
                "creado_en": "...", "funcion": { "...": "..." },
                "cliente": { "id": 4, "nombre": "Luis Gómez", "documento": "80123456", "contacto": "3109876543" },
                "entradas": [ { "id": 3, "codigo": "SIV-4YU94EJ5W9D4", "fila": "B", "numero": 9, "estado": "activa", "usada_en": null } ] } ] }
```
Error: `422 FECHA_INVALIDA`.

---

## Entradas

Permisos: el cliente **dueño** de la entrada, **cualquier** taquillero y el administrador. Otro cliente
recibe `403 ENTRADA_AJENA`. Ambos endpoints: `404 ENTRADA_NO_ENCONTRADA`.

### `GET /api/entradas/{id}`
**Rol:** cliente (dueño), taquillero, administrador.
```json
{ "entrada": { "id": 1, "codigo": "SIV-ST4H2YWQ3XBS", "estado": "activa", "fila": "A", "numero": 1,
               "usada_en": null, "funcion_id": 1, "compra_id": 1 } }
```

### `GET /api/entradas/{id}/qr`
**Rol:** cliente (dueño), taquillero, administrador. Responde la **imagen PNG** (`Content-Type: image/png`)
del código QR del `codigo` de la entrada. Como requiere cabecera `Authorization`, en el frontend se pide con
`fetch` y se muestra con `URL.createObjectURL(await respuesta.blob())`; un `<img src>` directo no envía el token.

---

## Validaciones

### `POST /api/validaciones`
**Rol:** taquillero, administrador. Valida una entrada en la puerta. Se bloquea la fila de la entrada: si dos
personas validan el mismo código a la vez, una recibe `valida` y la otra `ya_usada`. **Todos** los intentos
quedan registrados.
```json
{ "codigo": "SIV-ST4H2YWQ3XBS", "funcion_id": 1 }
```
`funcion_id` es opcional. El código se normaliza (sin espacios, en mayúsculas).

**Responde `200` en todos los resultados de negocio** (también los rechazos); mira `resultado` y `acceso_permitido`:

| `resultado` | `acceso_permitido` | Significado |
|---|---|---|
| `valida` | `true` | Acceso concedido; la entrada pasa a `usada` |
| `ya_usada` | `false` | Ya se usó; `primer_uso` trae fecha y taquillero |
| `invalida` | `false` | El código no existe (`entrada` y `funcion` son `null`) |
| `otra_funcion` | `false` | Es de otra función, o se lee fuera de la ventana horaria (desde `VALIDACION_ANTICIPACION_MINUTOS` antes del inicio, 120 por defecto, hasta la hora de fin) |
| `anulada` | `false` | La función se canceló |

Ejemplo `valida`:
```json
{ "resultado": "valida", "acceso_permitido": true, "mensaje": "Acceso permitido.", "validacion_id": 1,
  "entrada": { "id": 1, "codigo": "SIV-ST4H2YWQ3XBS", "fila": "A", "numero": 1, "estado": "usada" },
  "funcion": { "id": 1, "pelicula": "Intensa-Mente 2", "sala": "Sala Principal", "inicio": "2026-11-03T22:44:03-05:00" },
  "primer_uso": null }
```
Ejemplo `ya_usada` (`primer_uso`):
```json
{ "resultado": "ya_usada", "acceso_permitido": false, "mensaje": "La entrada ya fue utilizada.",
  "primer_uso": { "fecha": "2026-11-03T21:59:03-05:00", "taquillero": "Taquillero Prueba" }, "...": "..." }
```
Ejemplo `invalida`:
```json
{ "resultado": "invalida", "acceso_permitido": false, "mensaje": "La entrada no es válida.",
  "entrada": null, "funcion": null, "primer_uso": null, "validacion_id": 3 }
```
`otra_funcion` y `ya_usada` incluyen `funcion` con la función **a la que sí pertenece** la entrada.

Errores (solo el cuerpo inválido usa 422): `422 CODIGO_REQUERIDO`, `422 FUNCION_INVALIDA` (`funcion_id` no entero).

### `GET /api/validaciones`
**Rol:** taquillero (solo las suyas), administrador (todas). Filtros: `?resultado=valida|ya_usada|invalida|otra_funcion|anulada`,
`?desde=` / `?hasta=` (`YYYY-MM-DD`) y `?limite=` (entero de 1 a 1000).
```json
{ "validaciones": [ { "id": 1, "codigo_leido": "SIV-ST4H2YWQ3XBS", "resultado": "valida",
                      "fecha": "2026-11-03T21:59:03-05:00", "taquillero": "Taquillero Prueba",
                      "entrada_id": 1, "detalle": "Acceso permitido" } ] }
```
Errores: `422 RESULTADO_INVALIDO`, `422 LIMITE_INVALIDO`, `422 FECHA_INVALIDA`.

---

## Reportes (administrador)

Todos son `GET`, solo administrador, bajo `/api/reportes/`.

**Definiciones**

| Indicador | Definición |
|---|---|
| `ventas_totales` | Suma de `compras.total` aprobadas de funciones **no canceladas** |
| `ingresos_anulados` | Suma de `compras.total` aprobadas de funciones **canceladas** |
| `entradas_vendidas` | Entradas `activa` o `usada` (excluye anuladas) |
| `entradas_anuladas` | Entradas `anulada` |
| `ocupacion` | Asientos vendidos ÷ capacidad de la sala (%) |
| `tasa_perdida` | Reservas expiradas ÷ total de reservas del periodo (%) |

Los ingresos salen siempre de `compras.total`, no del precio actual de la función.

**Filtros de fecha** `?desde=YYYY-MM-DD&hasta=YYYY-MM-DD` (hora de Bogotá): si se envían ambos, `desde <= hasta`
y máximo 2 años; sin filtros se consideran todos los datos. Los reportes de **eventos** (ranking, reservas
vencidas, intentos rechazados, exportar ventas/validaciones) filtran por la fecha del evento; los reportes
**por función** (ventas por función, ocupación, asistencia) filtran por la fecha de inicio de la función.

Errores comunes de reportes: `422 RANGO_INVALIDO` ("desde posterior a hasta"), `422 RANGO_MUY_AMPLIO` (más de 2 años),
`422 FECHA_INVALIDA` (formato distinto de `YYYY-MM-DD`).

### `GET /api/reportes/resumen?dias=30`
`dias` de 1 a 730 (por defecto 30). Error propio: `422 DIAS_INVALIDOS`.
```json
{ "periodo": { "dias": 30, "desde": "2026-10-04T21:59:04-05:00", "hasta": "2026-11-03T21:59:04-05:00" },
  "ventas_totales": 120000, "ingresos_anulados": 30000, "entradas_vendidas": 6, "entradas_anuladas": 1,
  "usuarios_registrados": 6, "usuarios_total": 6, "funciones_activas": 2, "ocupacion_promedio": 25.0,
  "variacion": { "ventas_totales": null, "ingresos_anulados": null, "entradas_vendidas": null,
                 "entradas_anuladas": null, "usuarios_registrados": null } }
```
- `variacion` es el cambio porcentual contra el periodo anterior de igual duración; `null` si no hubo datos previos.
- `funciones_activas` (activas y futuras) y `ocupacion_promedio` son una foto actual, sin variación.
  `ocupacion_promedio` promedia las funciones no canceladas que inician dentro del periodo o después.
- `usuarios_registrados` = nuevos en el periodo; `usuarios_total` = todos.

### `GET /api/reportes/ventas-por-mes?meses=12`
`meses` de 1 a 24 (por defecto 12). Agrupa en **hora de Bogotá** y rellena con ceros los meses sin datos
(para la gráfica de línea). Error propio: `422 MESES_INVALIDOS`.
```json
{ "meses": 3, "serie": [ { "mes": "2026-09", "ventas": 0, "entradas": 0 },
                         { "mes": "2026-10", "ventas": 0, "entradas": 0 },
                         { "mes": "2026-11", "ventas": 120000, "entradas": 6 } ] }
```

### `GET /api/reportes/ventas-por-funcion`
Filtros `desde`, `hasta` (por fecha de inicio de la función). Funciones **no canceladas**, ordenadas por inicio.
```json
{ "funciones": [ { "funcion_id": 1, "pelicula": "Intensa-Mente 2", "sala": "Sala Principal",
                   "inicio": "2026-11-03T22:44:03-05:00", "entradas_vendidas": 5, "ingresos": 100000 } ] }
```

### `GET /api/reportes/ocupacion`
Filtros `desde`, `hasta`. Por función no cancelada; `reservados_vigentes` cuenta reservas activas que no han vencido.
```json
{ "funciones": [ { "funcion_id": 1, "pelicula": "Intensa-Mente 2", "sala": "Sala Principal",
                   "inicio": "2026-11-03T22:44:03-05:00", "capacidad": 72, "vendidos": 5,
                   "reservados_vigentes": 1, "porcentaje": 6.9 } ] }
```

### `GET /api/reportes/peliculas-ranking?orden=desc&limite=5`
`orden` `desc` (más vendidas, por defecto) o `asc` (menos vendidas); `limite` de 1 a 100 (por defecto 5);
filtros `desde`, `hasta` (por fecha de compra). `participacion` es el % sobre el total de entradas vendidas.
Errores propios: `422 ORDEN_INVALIDO`, `422 LIMITE_INVALIDO`.
```json
{ "orden": "desc", "limite": 5, "total_entradas": 6,
  "ranking": [ { "posicion": 1, "pelicula_id": 1, "pelicula": "Intensa-Mente 2",
                 "entradas_vendidas": 5, "participacion": 83.3 } ] }
```

### `GET /api/reportes/reservas-vencidas`
Filtros `desde`, `hasta` (por fecha de reserva).
```json
{ "total_reservas": 9, "expiradas": 1, "convertidas": 7, "canceladas": 0, "activas": 1, "tasa_perdida": 11.1 }
```

### `GET /api/reportes/asistencia`
Filtros `desde`, `hasta`. Entradas usadas ÷ vendidas, global y por función (no canceladas con ventas).
```json
{ "global": { "entradas_vendidas": 6, "entradas_usadas": 1, "porcentaje": 16.7 },
  "por_funcion": [ { "funcion_id": 3, "pelicula": "Película 3", "sala": "Sala 3",
                     "inicio": "2026-11-03T22:30:00-05:00", "entradas_vendidas": 1,
                     "entradas_usadas": 1, "porcentaje": 100.0 } ] }
```

### `GET /api/reportes/intentos-rechazados`
Filtros `desde`, `hasta`. Conteo de validaciones rechazadas por resultado y los últimos 50 intentos.
```json
{ "total_rechazados": 3,
  "por_resultado": { "invalida": 1, "ya_usada": 1, "otra_funcion": 1, "anulada": 0 },
  "ultimos": [ { "id": 4, "fecha": "2026-11-03T21:59:04-05:00", "codigo_leido": "SIV-VWBCGVR39W25",
                 "resultado": "otra_funcion", "taquillero": "Taquillero Prueba",
                 "detalle": "Pertenece a la función 1" } ] }
```

### `GET /api/reportes/exportar?tipo=ventas&desde=&hasta=`
`tipo`: `ventas`, `ocupacion`, `ranking` o `validaciones`. Devuelve un **CSV** (no JSON):

- `Content-Type: text/csv; charset=utf-8` y `Content-Disposition: attachment; filename="sivec_<tipo>_<AAAA-MM-DD>.csv"`.
- UTF-8 **con BOM** y separador `;` (abre bien en Excel en español); decimales con coma.
- Las celdas de texto que empiezan por `=`, `+`, `-` o `@` llevan una comilla simple delante (protección contra inyección de fórmulas).
- `ventas` incluye todas las compras aprobadas del periodo, con la columna `funcion_cancelada` (`Sí`/`No`) para poder conciliar con `ventas_totales`.

Para leer el nombre del archivo desde el frontend, la API expone la cabecera `Content-Disposition` por CORS.
Error propio: `422 TIPO_INVALIDO`.

```
numero;fecha;cliente;documento;contacto;pelicula;sala;inicio_funcion;entradas;total;metodo_pago;registrada_por;funcion_cancelada
C-000001;2026-11-03T21:59:03-05:00;Cliente Prueba;;;Intensa-Mente 2;Sala Principal;2026-11-03T22:44:03-05:00;2;44000;tarjeta;Cliente Prueba;Sí
```

---

## Flujo típico del frontend

**Compra del cliente**
1. `POST /auth/login` (o `/auth/registro`) → guardar `token`.
2. `GET /peliculas` → `GET /funciones?pelicula_id=` → `GET /funciones/{id}/asientos` (con token, para ver `mio`).
3. El cliente elige asientos → `POST /reservas` → iniciar el temporizador con `segundos_restantes`.
   - `409 ASIENTO_NO_DISPONIBLE`: otra persona ganó el asiento; recargar el mapa.
   - Botón "Volver": `POST /reservas/cancelar`.
4. `POST /compras` con `metodo_pago: "tarjeta"` (y `resultado_simulado` para la demo).
   - `201`: mostrar las `entradas`; cada QR con `GET /entradas/{id}/qr`.
   - `402 PAGO_RECHAZADO`: los asientos siguen reservados hasta `detalle.vence_en`; permitir reintentar.
   - `409 RESERVA_VENCIDA`: volver al mapa.
5. `GET /mis-compras` para el historial.

**Venta en taquilla**: `POST /compras` con `cliente: {nombre, ...}` y `metodo_pago: "efectivo"` o `"tarjeta"`; historial con `GET /ventas`.

**Puerta**: `POST /validaciones` con el código leído (y `funcion_id` de la función en curso); mostrar `mensaje` y usar
`acceso_permitido` para el color verde/rojo.

**Administración**: CRUD de películas, salas y funciones; `POST /funciones/{id}/cancelar` y `GET /funciones/{id}/afectados`
para el reembolso; reportes y exportación CSV.
