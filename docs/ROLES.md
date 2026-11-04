# Matriz de endpoints y roles

> Archivo **generado automáticamente** con `python -m scripts.generar_roles`.
> No lo edites a mano: cambia el decorador `@rol_requerido` en el código y vuelve a generarlo.

- **Público**: no requiere sesión.
- **Cualquier usuario autenticado**: requiere token, sin restricción de rol.
- Los permisos se validan SIEMPRE en el servidor (RNF-10): sin token responde `401`; con un rol no permitido, `403`.
- La prueba `tests/test_roles.py` recorre todas estas rutas y verifica esos códigos.

| Método | Ruta | Público | Cliente | Taquillero | Administrador | Descripción |
|---|---|:-:|:-:|:-:|:-:|---|
| POST | `/api/auth/login` | ✔ | ✔ | ✔ | ✔ | Inicio de sesión: valida credenciales y devuelve token + usuario. |
| POST | `/api/auth/registro` | ✔ | ✔ | ✔ | ✔ | Registro público: crea un usuario cliente y su ficha de cliente. |
| GET | `/api/auth/yo` | — | ✔ | ✔ | ✔ | Devuelve los datos del usuario autenticado a partir del token. |
| POST | `/api/compras` | — | ✔ | ✔ | — | Confirma una compra y simula el pago (cliente o taquillero). |
| GET | `/api/entradas/<int:entrada_id>` | — | ✔ | ✔ | ✔ | Detalle de una entrada (dueño, taquillero o administrador). |
| GET | `/api/entradas/<int:entrada_id>/qr` | — | ✔ | ✔ | ✔ | Devuelve la imagen PNG del código QR de la entrada. |
| GET | `/api/funciones` | ✔ | ✔ | ✔ | ✔ | Público: funciones activas y futuras de películas activas. |
| POST | `/api/funciones` | — | — | — | ✔ | Administrador: crea una función y genera sus asientos. |
| DELETE | `/api/funciones/<int:funcion_id>` | — | — | — | ✔ | Administrador: elimina una función si no tiene ventas. |
| GET | `/api/funciones/<int:funcion_id>` | ✔ | ✔ | ✔ | ✔ | Público: detalle de una función (incluye iniciadas, con su estado). |
| PUT | `/api/funciones/<int:funcion_id>` | — | — | — | ✔ | Administrador: edita una función (reglas de ventas e inicio). |
| GET | `/api/funciones/<int:funcion_id>/afectados` | — | — | — | ✔ | Administrador: compras afectadas por la función (para reembolso). |
| GET | `/api/funciones/<int:funcion_id>/asientos` | ✔ | ✔ | ✔ | ✔ | Público (token opcional): mapa de asientos de la función. |
| POST | `/api/funciones/<int:funcion_id>/cancelar` | — | — | — | ✔ | Administrador: cancela la función y anula sus entradas activas. |
| GET | `/api/mis-compras` | — | ✔ | — | — | Cliente: sus compras aprobadas con función, película y entradas. |
| GET | `/api/peliculas` | ✔ | ✔ | ✔ | ✔ | Público: lista solo las películas activas (cartelera). |
| POST | `/api/peliculas` | — | — | — | ✔ | Administrador: crea una película. |
| DELETE | `/api/peliculas/<int:pelicula_id>` | — | — | — | ✔ | Administrador: DELETE lógico (desactiva), nunca borra. |
| GET | `/api/peliculas/<int:pelicula_id>` | ✔ | ✔ | ✔ | ✔ | Público: detalle de una película activa. |
| PUT | `/api/peliculas/<int:pelicula_id>` | — | — | — | ✔ | Administrador: edita una película. |
| GET | `/api/reportes/asistencia` | — | — | — | ✔ | Entradas usadas / vendidas, global y por función. |
| GET | `/api/reportes/exportar` | — | — | — | ✔ | Exporta un reporte a CSV (?tipo=ventas|ocupacion|ranking|validaciones). |
| GET | `/api/reportes/intentos-rechazados` | — | — | — | ✔ | Conteo de validaciones rechazadas y los últimos 50 intentos. |
| GET | `/api/reportes/ocupacion` | — | — | — | ✔ | Ocupación por función no cancelada. |
| GET | `/api/reportes/peliculas-ranking` | — | — | — | ✔ | Ranking de películas por entradas vendidas (?orden=desc|asc&limite=5). |
| GET | `/api/reportes/reservas-vencidas` | — | — | — | ✔ | Reservas expiradas, total de reservas y tasa de pérdida. |
| GET | `/api/reportes/resumen` | — | — | — | ✔ | Indicadores generales de los últimos N días (?dias=30). |
| GET | `/api/reportes/ventas-por-funcion` | — | — | — | ✔ | Entradas vendidas e ingresos por función. |
| GET | `/api/reportes/ventas-por-mes` | — | — | — | ✔ | Serie mensual de ventas y entradas (?meses=12). |
| POST | `/api/reservas` | — | ✔ | ✔ | — | Reserva uno o varios asientos de una función (cliente o taquillero). |
| POST | `/api/reservas/cancelar` | — | ✔ | ✔ | — | Cancela todas mis reservas activas en una función (botón 'Volver'). |
| GET | `/api/reservas/mias` | — | ✔ | ✔ | — | Lista mis reservas activas en una función (?funcion_id=). |
| DELETE | `/api/reservas/<int:reserva_id>` | — | ✔ | ✔ | — | Cancela una reserva propia y activa. |
| GET | `/api/salas` | — | — | ✔ | ✔ | Lista todas las salas (administrador y taquillero). |
| POST | `/api/salas` | — | — | — | ✔ | Administrador: crea una sala y calcula su capacidad. |
| DELETE | `/api/salas/<int:sala_id>` | — | — | — | ✔ | Administrador: elimina una sala si no tiene funciones. |
| GET | `/api/salas/<int:sala_id>` | — | — | ✔ | ✔ | Detalle de una sala (administrador y taquillero). |
| PUT | `/api/salas/<int:sala_id>` | — | — | — | ✔ | Administrador: edita una sala. |
| GET | `/api/salud` | ✔ | ✔ | ✔ | ✔ | Devuelve el estado de la API y de la base de datos. |
| GET | `/api/usuarios` | — | — | — | ✔ | Lista los usuarios. Filtro opcional por rol: ?rol=taquillero. |
| POST | `/api/usuarios` | — | — | — | ✔ | Crea un usuario taquillero o administrador. |
| DELETE | `/api/usuarios/<int:usuario_id>` | — | — | — | ✔ | Desactiva un usuario (no lo elimina de la base de datos). |
| PUT | `/api/usuarios/<int:usuario_id>` | — | — | — | ✔ | Edita un usuario existente. |
| GET | `/api/validaciones` | — | — | ✔ | ✔ | Historial de validaciones (taquillero: propias; admin: todas). |
| POST | `/api/validaciones` | — | — | ✔ | ✔ | Valida un código de entrada. Responde 200 en todos los resultados. |
| GET | `/api/ventas` | — | — | ✔ | ✔ | Historial de ventas: taquillero (propias) o administrador (todas). |

Total de endpoints: 46.
