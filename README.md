# SIVEC API

**SIVEC** es un Sistema de Venta de Entradas para cine/eventos (proyecto universitario). Este repositorio es el
**backend**: una API REST en Flask + PostgreSQL que usa el frontend en React.

Qué hace:

- Catálogo público de películas, salas y funciones, con **mapa de asientos** en tiempo real.
- **Reservas temporales** (5 minutos) y **compra con pago simulado**, con generación de entradas con código único y **QR**.
- **Validación en puerta** de entradas (una sola vez, con registro de todos los intentos).
- Roles: **cliente**, **taquillero** y **administrador** (permisos validados siempre en el servidor).
- Administración de películas, salas, funciones y usuarios; **cancelación de funciones** con anulación de entradas y lista para reembolso.
- **Reportes** e indicadores, con exportación a CSV.
- Concurrencia segura: dos personas no pueden reservar, comprar ni validar lo mismo a la vez (bloqueos de fila en PostgreSQL).

## Stack

Python 3.11+ (probado con 3.12) · Flask 3 · PostgreSQL 14+ (probado con 17) · Flask-SQLAlchemy / Flask-Migrate (Alembic) ·
Flask-JWT-Extended · bcrypt · Flask-CORS · APScheduler · qrcode · pytest.

## Requisitos

| Programa | Versión | Para qué |
|---|---|---|
| Python | 3.11 o superior | Ejecutar la API (`python --version`) |
| PostgreSQL | 14 o superior | Base de datos (incluye `psql`, `pg_dump`, `pg_restore`) |
| Git | cualquiera | Obtener el código |

## Instalación paso a paso (Windows)

Todos los comandos son de **PowerShell**, desde la carpeta del proyecto.

### 1. Obtener el código

```powershell
git clone <URL-del-repositorio> sivec-api
cd sivec-api
```

### 2. Crear las bases de datos en PostgreSQL

Necesitas dos: `sivec` (la de trabajo) y `sivec_test` (solo para las pruebas automáticas, **se vacía en cada prueba**).

```powershell
psql -U postgres -c "CREATE DATABASE sivec;"
psql -U postgres -c "CREATE DATABASE sivec_test;"
```

Si `psql` no se reconoce, usa la ruta completa
(`& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -c "..."`) o crea las bases desde pgAdmin.
(Si no creas `sivec_test`, las pruebas la crean solas.)

### 3. Entorno virtual y dependencias

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Si PowerShell dice que la ejecución de scripts está deshabilitada:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y vuelve a activar el entorno.

### 4. Configurar el `.env`

```powershell
Copy-Item .env.example .env
notepad .env
```

Completa como mínimo:

| Variable | Qué poner |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://postgres:TU_CLAVE@localhost:5432/sivec` |
| `TEST_DATABASE_URL` | La misma conexión pero con la base `sivec_test` (**debe ser otra base y su nombre debe incluir «test»**) |
| `SECRET_KEY` y `JWT_SECRET_KEY` | Dos cadenas largas y aleatorias distintas |
| `CORS_ORIGENES` | Dirección del frontend, p. ej. `http://localhost:5173` |

Si tu contraseña tiene caracteres especiales (`@`, `:`, `/`, `#`), escríbela codificada: `@` → `%40`, `:` → `%3A`.
El resto de variables (duración de la reserva, límites, etc.) tienen valores por defecto sensatos; están explicadas en `.env.example`.
**Nunca subas el `.env` a git** (ya está en el `.gitignore`).

### 5. Crear las tablas (migraciones)

```powershell
flask --app run db upgrade
```

### 6. Cargar datos de prueba

```powershell
flask --app run seed
```

Es **idempotente** (puedes repetirlo sin duplicar datos) y crea funciones con fechas relativas a hoy, así que conviene
volver a ejecutarlo cada pocos días para que haya funciones futuras. Crea:

| Usuario | Rol | Contraseña |
|---|---|---|
| `cliente@sivec.com` | cliente | `123456` |
| `taquillero@sivec.com` | taquillero | `123456` |
| `admin@sivec.com` | administrador | `123456` |

más 7 películas, 2 salas, varias funciones y algunas ventas y reservas de ejemplo.

## Ejecutar la API

```powershell
python run.py
```

La API queda en `http://localhost:5000/api`. Por seguridad escucha **solo en tu equipo** (`127.0.0.1`). Si otros equipos de la
red deben acceder (por ejemplo, un compañero con el frontend), define en el `.env` `FLASK_HOST=0.0.0.0` y
`FLASK_ENV=production` (así no queda activo el depurador interactivo, que permite ejecutar código; en producción
`SECRET_KEY` y `JWT_SECRET_KEY` son obligatorias). Puerto: `FLASK_PORT`.

Comprueba que responde:

```powershell
Invoke-RestMethod http://localhost:5000/api/salud
```

```
estado base_datos servicio  hora_utc
------ ---------- --------  --------
ok     ok         sivec-api 2026-11-04T02:59:01+00:00
```

Al iniciar, un proceso en segundo plano (APScheduler) libera cada 30 segundos las reservas vencidas.

Probar un inicio de sesión:

```powershell
$login = Invoke-RestMethod http://localhost:5000/api/auth/login -Method Post -ContentType application/json `
  -Body (@{ correo = "admin@sivec.com"; password = "123456" } | ConvertTo-Json)
Invoke-RestMethod http://localhost:5000/api/auth/yo -Headers @{ Authorization = "Bearer $($login.token)" }
```

Para probar todos los endpoints con ejemplos, importa la colección de Postman de [`docs/postman/`](docs/postman).

## Ejecutar las pruebas

```powershell
python -m pytest -v
```

Son 95 pruebas (≈ 1,5 minutos) que cubren los criterios de aceptación (CA-01 a CA-17), la concurrencia con hilos reales,
los reportes, los permisos de **todas** las rutas, la robustez ante datos inválidos y los tiempos de respuesta.

- Usan **PostgreSQL real** y la base `TEST_DATABASE_URL` (`sivec_test`). **Nunca tocan la base de trabajo**: si
  `TEST_DATABASE_URL` falta, apunta a la misma base que `DATABASE_URL` o su nombre no incluye «test», se niegan a ejecutarse.
- El esquema de la base de pruebas se construye con las migraciones reales.

Variantes útiles:

```powershell
python -m pytest -v -m concurrencia                 # solo las pruebas de concurrencia
python -m pytest tests/test_rendimiento.py -v -s    # tabla de tiempos de respuesta (RNF-03, < 3 s)
python -m pytest tests/test_reservas.py -v          # un solo archivo
```

## Respaldo y restauración

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1     # crea backups\sivec_AAAAMMDD_HHmm.dump
powershell -ExecutionPolicy Bypass -File .\scripts\restore.ps1    # restaura el último en sivec_restore y cuenta filas
```

Detalles, opciones y cómo programar el respaldo diario en Windows: [`docs/RESPALDO.md`](docs/RESPALDO.md).

## Estructura del proyecto

```
sivec-api/
  app/
    __init__.py        Application factory (create_app)
    config.py          Configuración por entorno (development / testing / production)
    extensions.py      db, migrate, jwt, cors
    scheduler.py       Job que libera reservas vencidas
    models/            Un archivo por tabla (11 modelos) + enums
    routes/            Blueprints: solo reciben la petición y responden
    services/          Lógica de negocio: reservas, compras, validaciones, reportes...
    utils/             Errores, roles (@rol_requerido), tiempo, validaciones, CSV, códigos
  migrations/          Migraciones de Alembic
  tests/               Pruebas con pytest
  scripts/             seed, backup/restore (.ps1) y generadores de documentación
  docs/                Documentación y colección de Postman
  .env.example         Plantilla de configuración (sin secretos)
  requirements.txt     Dependencias con versión fija
  run.py               Punto de entrada
```

## Documentación

| Documento | Contenido |
|---|---|
| [`docs/API.md`](docs/API.md) | **Todos los endpoints**: método, ruta, rol, cuerpo, respuesta y errores (para conectar el frontend) |
| [`docs/ROLES.md`](docs/ROLES.md) | Matriz de endpoints y roles (generada desde el código) |
| [`docs/MODELO_DATOS.md`](docs/MODELO_DATOS.md) | Tablas, enumeraciones, índices y diagrama entidad-relación |
| [`docs/RESPALDO.md`](docs/RESPALDO.md) | Respaldo, restauración y tarea programada |
| [`docs/postman/`](docs/postman) | Colección y entorno de Postman |

## Comandos útiles

```powershell
flask --app run routes                         # lista de endpoints
flask --app run db migrate -m "descripcion"    # generar una migración tras cambiar un modelo
flask --app run db upgrade                     # aplicar migraciones
flask --app run seed                           # datos de prueba
python -m scripts.generar_roles                # regenerar docs/ROLES.md
python -m scripts.generar_postman              # regenerar la colección de Postman
```

Si cambias un modelo, genera la migración: la prueba `test_modelos_y_migraciones_estan_sincronizados` falla si se olvida.
Si agregas una ruta, ponle `@rol_requerido(...)`: la prueba de roles falla si queda abierta por descuido.

## Reglas de negocio importantes

- Un asiento tiene un solo estado (`disponible`, `reservado`, `vendido`) y no se puede tomar si ya está ocupado.
- La reserva dura 5 minutos (`RESERVA_DURACION_MINUTOS`); al vencer, el asiento vuelve a estar disponible.
- Reservar, comprar y validar ocurren en **una transacción** con `SELECT ... FOR UPDATE`; si algún asiento falla, no se hace nada.
- Un pago rechazado no genera entradas y deja los asientos reservados hasta que venza la reserva.
- Cada entrada tiene un código único y se usa **una sola vez**; solo vale para su función y asiento.
- Al cancelar una función, sus entradas activas pasan a «anulada».
- Todas las fechas se guardan en UTC y la API las devuelve en hora de Bogotá (UTC-5).

## Solución de problemas

| Síntoma | Causa y solución |
|---|---|
| `RuntimeError: Either 'SQLALCHEMY_DATABASE_URI'... must be set` | No existe `.env` o le falta `DATABASE_URL`. Ejecuta `Copy-Item .env.example .env` y complétalo. |
| `password authentication failed for user "postgres"` | La clave del `DATABASE_URL` es incorrecta. Si tiene caracteres especiales, codifícala (`@` → `%40`). |
| `database "sivec" does not exist` | Crea la base: `psql -U postgres -c "CREATE DATABASE sivec;"` |
| `relation "usuarios" does not exist` | Faltan las tablas: `flask --app run db upgrade` |
| `psql no se reconoce como un comando` | Agrega `C:\Program Files\PostgreSQL\17\bin` al `PATH` o usa la ruta completa. |
| `connection refused` / no conecta | PostgreSQL no está iniciado. Abre «Servicios» de Windows e inicia `postgresql-x64-17`. |
| `Activate.ps1 ... la ejecución de scripts está deshabilitada` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `Address already in use` (puerto 5000) | Otro programa usa el 5000. Ciérralo o cambia `FLASK_PORT` en el `.env`. |
| Otro equipo no llega a la API (`connection refused`) | La API escucha solo en `127.0.0.1`. Ver «Ejecutar la API» para abrirla a la red de forma segura (`FLASK_HOST`). |
| El frontend recibe un error de CORS | Agrega su dirección exacta (con puerto) a `CORS_ORIGENES` en el `.env` y reinicia la API. |
| `401 TOKEN_VENCIDO` | La sesión expiró (`JWT_EXPIRACION_MINUTOS`). Inicia sesión de nuevo. |
| La cartelera está vacía | Las funciones del seed duran 7 días desde que se cargaron. Vuelve a ejecutar `flask --app run seed`. |
| Una validación responde `otra_funcion` aunque el código es correcto | Solo se acepta desde 120 min antes del inicio de la función hasta que termina (`VALIDACION_ANTICIPACION_MINUTOS`). |
| `pytest`: `Falta TEST_DATABASE_URL` / `debe llevar 'test'` / `misma base` | Define `TEST_DATABASE_URL` en el `.env` con una base **distinta** cuyo nombre incluya «test». |
| `ModuleNotFoundError: No module named 'app'` al probar | Ejecuta `python -m pytest` desde la raíz del proyecto (no `pytest` desde otra carpeta). |
| `flask` dice que no encuentra la aplicación | Usa `flask --app run <comando>` o agrega `FLASK_APP=run.py` al `.env`. |
| Las reservas vencidas no se liberan solas | El job corre al iniciar la API con `python run.py` (cada 30 s). Aunque no corra, la API ignora las vencidas al leer y reservar. |
| `pip install` falla compilando `psycopg2` | Este proyecto usa `psycopg2-binary`; actualiza pip (`python -m pip install --upgrade pip`) y usa Python 3.11–3.12. |
