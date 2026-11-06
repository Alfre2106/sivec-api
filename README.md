# SIVEC API (backend)

**Sistema de Venta de Entradas para Eventos/Cine (SIVEC)**: API REST en Flask con base de datos PostgreSQL.
Proyecto final de *Administración de Sistemas de Información* (Ingeniería de Sistemas y Computación, semestre VIII, CUL).

Este repositorio es el **backend**. La interfaz web está en el repositorio **sivec-front** (ver sección 6).

> Aviso: es un proyecto académico. El pago es **simulado** (no se procesa ningún pago real) y los pósters y nombres de películas son solo datos de prueba.

---

## 1. Cómo se conectan las piezas

El sistema tiene **tres partes que deben estar encendidas a la vez**:

```
 NAVEGADOR (interfaz React)          API (este proyecto)             BASE DE DATOS
 http://localhost:5173      --->     http://localhost:5000/api  --->  PostgreSQL (puerto 5432)
 repositorio sivec-front            repositorio sivec-api            bases: sivec y sivec_test
```

La interfaz nunca habla con la base de datos: solo la API lo hace. Por eso las reglas (un asiento no se vende dos veces, permisos por rol) se cumplen siempre.

| Pieza | Puerto | Quién la enciende |
|---|---|---|
| PostgreSQL | 5432 | Servicio de Windows (queda activo al instalarlo) |
| API Flask | 5000 | `python run.py` en este repositorio |
| Interfaz React | 5173 | `npm run dev` en el repositorio sivec-front |

---

## 2. Requisitos

- **Windows** con PowerShell (los comandos de esta guía son para PowerShell)
- **Git**
- **Python 3.11 o superior** (`python --version`)
- **PostgreSQL 16 o 17** (el proyecto se desarrolló con la 17). Anota la contraseña del usuario `postgres`
- **Node.js 20 LTS o superior** (solo para la interfaz; `node --version`)
- Navegador actual: Chrome, Edge o Firefox

No hace falta pgAdmin: todo se puede hacer con `psql`, que viene con PostgreSQL.

---

## 3. Instalación del backend, paso a paso

Se recomienda clonar ambos repositorios en la misma carpeta, por ejemplo `C:\proyectos\`.

### 3.1 Clonar

```powershell
cd C:\proyectos
git clone https://github.com/Alfre2106/sivec-api.git
cd sivec-api
```

### 3.2 Crear las bases de datos

Cambia `17` por tu versión de PostgreSQL si es otra. Te pedirá la contraseña de `postgres` (al escribirla no se ve nada, es normal):

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h localhost -c "CREATE DATABASE sivec;"
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h localhost -c "CREATE DATABASE sivec_test;"
```

`sivec` es la base real y `sivec_test` es solo para las pruebas automáticas. Si dice que ya existen, está bien.

### 3.3 Entorno virtual y dependencias

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Si PowerShell bloquea la activación, ejecuta una vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y repite.
Sabrás que el entorno está activo porque la línea empieza con `(venv)`. **Debes activarlo en cada terminal nueva.**

### 3.4 Variables de entorno (`.env`)

El archivo `.env` guarda tus claves y **nunca se sube a GitHub**. Cada integrante crea el suyo a partir de la plantilla:

```powershell
Copy-Item .env.example .env
notepad .env
```

Valores que debes cambiar:

| Variable | Qué poner |
|---|---|
| `SECRET_KEY` | Una cadena aleatoria larga (ver comando abajo) |
| `JWT_SECRET_KEY` | **Otra** cadena aleatoria, distinta de la anterior |
| `DATABASE_URL` | `postgresql+psycopg2://postgres:TU_CLAVE@localhost:5432/sivec` |
| `TEST_DATABASE_URL` | `postgresql+psycopg2://postgres:TU_CLAVE@localhost:5432/sivec_test` |

Para generar cada clave aleatoria (ejecútalo dos veces):

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Reglas del `.env`: sin comillas, sin espacios alrededor del `=`, y la contraseña de PostgreSQL **sin símbolos** como `@ : / # %` (rompen la dirección de conexión).

Variables que normalmente se dejan como vienen:

| Variable | Valor | Significado |
|---|---|---|
| `CORS_ORIGENES` | `http://localhost:5173,http://127.0.0.1:5173` | Direcciones desde las que la interfaz puede llamar a la API |
| `RESERVA_DURACION_MINUTOS` | `5` | Tiempo que dura una reserva de asientos |
| `VALIDACION_ANTICIPACION_MINUTOS` | `120` (o sin definir) | Una entrada se acepta desde 2 horas antes de la función hasta que termina |
| `ZONA_HORARIA` | `America/Bogota` | Las fechas se guardan en UTC y se muestran en hora de Colombia |
| `JWT_EXPIRACION_MINUTOS` | `120` | Duración de la sesión |

### 3.5 Crear las tablas y los datos de prueba

Con el entorno virtual activo:

```powershell
flask db upgrade
flask seed
```

`flask db upgrade` crea las 11 tablas. `flask seed` carga usuarios, salas, películas y funciones de ejemplo; se puede ejecutar más de una vez sin duplicar datos.

### 3.6 Encender la API

```powershell
python run.py
```

Comprueba que responde abriendo `http://localhost:5000/api/salud`. Debe mostrar `"base_datos": "ok"` y `"estado": "ok"`.
Deja esa terminal abierta: mientras esté corriendo, la API está encendida (se apaga con `Ctrl + C`).

---

## 4. Usuarios de prueba

La contraseña de los tres es `123456`:

| Correo | Rol | Qué puede hacer |
|---|---|---|
| `cliente@sivec.com` | Cliente | Ver cartelera, reservar, pagar (simulado), ver sus compras y entradas con QR |
| `taquillero@sivec.com` | Taquillero | Vender en taquilla, validar entradas, ver su historial de ventas |
| `admin@sivec.com` | Administrador | Gestionar películas, salas, funciones y usuarios, cancelar funciones, ver reportes |

Un cliente nuevo también puede registrarse desde la interfaz. Estas contraseñas son solo para desarrollo local.

---

## 5. Pruebas automáticas

Con el entorno activo y la base `sivec_test` creada:

```powershell
python -m pytest -v
```

Las pruebas usan `sivec_test` y no tocan los datos de `sivec`. Incluyen la prueba de concurrencia: dos reservas simultáneas del mismo asiento, de las que solo una se confirma.

---

## 6. Levantar TODO el sistema a la vez (backend + frontend)

Necesitas **dos terminales abiertas al mismo tiempo** (por ejemplo, una ventana del editor por proyecto). Los repositorios son: `sivec-api` (este) y `sivec-front`.

**Antes de empezar**, confirma que el servicio de PostgreSQL está iniciado (normalmente ya lo está; si no, en `services.msc` busca `postgresql-x64-17` y dale *Iniciar*).

**Terminal A: la API**

```powershell
cd C:\proyectos\sivec-api
venv\Scripts\Activate.ps1
python run.py
```

**Terminal B: la interfaz** (la primera vez, sigue antes la instalación del README de `sivec-front`)

```powershell
cd C:\proyectos\sivec-front
npm run dev
```

**Abrir el sistema:** `http://localhost:5173` en el navegador. **Escribe `localhost`, no `127.0.0.1`**, o el navegador puede bloquear las llamadas a la API.

**Comprobaciones rápidas**

1. `http://localhost:5000/api/salud` debe mostrar `"base_datos": "ok"`.
2. En `http://localhost:5173`, la cartelera debe mostrar películas con sus pósters.
3. Inicia sesión con `cliente@sivec.com` / `123456`.

**Para apagar todo:** `Ctrl + C` en cada terminal.

---

## 7. Reglas útiles para probar y presentar

- **Reserva:** dura 5 minutos; después el asiento vuelve a estar disponible.
- **Validación de entradas:** solo acepta entradas desde 2 horas antes de la función hasta que termina. Para probar una validación, compra entradas de una función que empiece pronto. Si el resultado es "otra función", la entrada no está dentro de esa ventana.
- **Funciones con fechas pasadas:** la cartelera solo muestra funciones futuras. Si las de prueba ya pasaron, créalas nuevas desde el panel del administrador (o consulta la carpeta `docs/`).
- **Pago simulado:** en la pantalla de pago hay una casilla para simular un pago rechazado.
- **Seguridad en desarrollo:** nunca subas el `.env` al repositorio y no uses estas contraseñas fuera de tu computador.

---

## 8. Respaldo y restauración de la base de datos

```powershell
scripts\backup.ps1
scripts\restore.ps1
```

El primero crea una copia en la carpeta `backups\` (conserva las últimas 14); el segundo la restaura en una base distinta para comprobar que funciona. Los detalles están en `docs\`.

---

## 9. Documentación

Dentro de la carpeta `docs\`:

- `API.md`: todos los endpoints con ejemplos de petición, respuesta y errores
- `MODELO_DATOS.md`: las tablas y su diagrama entidad-relación
- `ROLES.md`: qué rol puede usar cada endpoint
- `postman\`: colección y entorno de Postman para probar la API sin la interfaz

---

## 10. Solución de problemas

| Problema | Causa y solución |
|---|---|
| `No module named 'flask'` | El entorno virtual no está activo: ejecuta `venv\Scripts\Activate.ps1` |
| `Fatal error in launcher` al usar `pip` | El entorno se creó en otra carpeta o con otro nombre: bórralo (`Remove-Item -Recurse -Force venv`), créalo de nuevo y usa `python -m pip` |
| `password authentication failed` | La contraseña del `DATABASE_URL` no es la de PostgreSQL |
| `database "sivec" does not exist` | Falta crear la base (paso 3.2) |
| `connection refused` al conectar a la base | El servicio de PostgreSQL está detenido: inícialo desde `services.msc` |
| `/api/salud` dice `"base_datos"` con error | Revisa `DATABASE_URL` en el `.env` y que PostgreSQL esté activo |
| La interfaz dice "No se pudo conectar con el servidor" o error de CORS | La API no está corriendo, o abriste la interfaz como `127.0.0.1`. Usa `http://localhost:5173` y revisa `CORS_ORIGENES` |
| `Address already in use` (puerto 5000) | Otro programa usa ese puerto: ciérralo o reinicia la terminal anterior de la API |
| Cambié el `.env` y no pasa nada | El `.env` solo se lee al arrancar: detén la API (`Ctrl + C`) y vuelve a ejecutar `python run.py` |
| `Dubious ownership` en Git | Ejecuta el comando `git config --global --add safe.directory ...` que Git te muestra |

---

## 11. Trabajo en equipo con Git

- Antes de empezar a trabajar: `git pull`
- Crea una rama por tarea: `git checkout -b nombre-de-la-tarea`
- Guarda cambios: `git add .` y `git commit -m "mensaje claro"`
- Sube tu rama: `git push -u origin nombre-de-la-tarea` y abre un Pull Request en GitHub
- **Nunca** subas `.env`, `venv/`, `backups/` ni contraseñas. Si dudas, revisa `git status` antes del commit.

---

## 12. Equipo

Alfredo Leal, Edgar Rodelo, Miguelangel De La Hoz, Alejandro Arevalo y Haider Cantillo.
Programa: Ingeniería de Sistemas y Computación, semestre VIII. Asignatura: Administración de Sistemas de Información. Docente: Janer E. Pava.
