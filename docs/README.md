# SIVEC API

Sistema de Venta de Entradas para Eventos/Cine — Backend (API REST en Flask + PostgreSQL).

Proyecto universitario. La documentación técnica y la colección de Postman se
completarán en la Fase B7.

## Fase actual: B0 — Proyecto base

Incluye la estructura del proyecto, configuración por `.env`, conexión a
PostgreSQL, CORS, manejo uniforme de errores y el endpoint `GET /api/salud`.

### Requisitos previos

- Python 3.11+ (probado con 3.12)
- PostgreSQL 14+ (probado con 17)

### Puesta en marcha

```bash
# 1. Activar el entorno virtual
#    Windows (PowerShell):
.\venv\Scripts\Activate.ps1
#    Linux/Mac:
#    source venv/bin/activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Crear la base de datos en PostgreSQL
createdb sivec        # o: psql -U postgres -c "CREATE DATABASE sivec;"

# 4. Configurar variables de entorno
copy .env.example .env   # Windows
# cp .env.example .env    # Linux/Mac
# ...y editar .env con tus credenciales reales

# 5. Arrancar la API
python run.py
```

### Probar el endpoint de salud

```bash
curl http://localhost:5000/api/salud
```

Respuesta esperada (200):

```json
{
  "estado": "ok",
  "servicio": "sivec-api",
  "base_datos": "ok",
  "hora_utc": "2026-11-02T10:00:00+00:00"
}
```

## Reportes e indicadores (`/api/reportes/*`, solo administrador)

### Definiciones

| Indicador | Definición |
|---|---|
| `ventas_totales` | Suma de `compras.total` con `estado_pago = aprobado` de funciones **no canceladas**. |
| `ingresos_anulados` | Suma de `compras.total` aprobadas de funciones **canceladas**. |
| `entradas_vendidas` | Entradas en estado `activa` o `usada` (excluye anuladas). |
| `entradas_anuladas` | Entradas en estado `anulada`. |
| `ocupacion` | Asientos vendidos / capacidad de la sala (%). |
| `tasa_perdida` | Reservas expiradas / total de reservas del periodo (%). |

Los ingresos salen siempre de `compras.total`, nunca del precio actual de la función.

### Filtros de fecha

`?desde=YYYY-MM-DD&hasta=YYYY-MM-DD`, interpretados en hora de Bogotá. Si se envían
ambos, debe cumplirse `desde <= hasta` y un máximo de 2 años. Sin filtros se
consideran todos los datos.

- Reportes de **eventos** (ranking, reservas vencidas, intentos rechazados, exportar
  ventas/validaciones) filtran por la fecha del evento (compra, reserva, validación).
- Reportes **por función** (ventas por función, ocupación, asistencia) filtran por la
  fecha de inicio de la función.
- Las series por mes agrupan en hora de Bogotá, no en UTC.

### Endpoints

| Endpoint | Parámetros | Notas |
|---|---|---|
| `GET /reportes/resumen` | `dias` (1-730, def. 30) | Incluye `variacion` (%) contra el periodo anterior de igual duración; `null` si no hubo datos previos. `funciones_activas` y `ocupacion_promedio` son una foto actual (sin variación). `usuarios_registrados` = nuevos en el periodo; `usuarios_total` = total. |
| `GET /reportes/ventas-por-mes` | `meses` (1-24, def. 12) | Serie `[{mes: "2026-11", ventas, entradas}]` con ceros en meses sin datos. |
| `GET /reportes/ventas-por-funcion` | `desde`, `hasta` | Entradas e ingresos por función no cancelada. |
| `GET /reportes/ocupacion` | `desde`, `hasta` | Por función no cancelada: capacidad, vendidos, reservados vigentes, %. |
| `GET /reportes/peliculas-ranking` | `orden` (asc/desc), `limite` (1-100, def. 5), `desde`, `hasta` | Incluye % de participación sobre el total. |
| `GET /reportes/reservas-vencidas` | `desde`, `hasta` | Expiradas, total y tasa de pérdida. |
| `GET /reportes/asistencia` | `desde`, `hasta` | Entradas usadas / vendidas, global y por función. |
| `GET /reportes/intentos-rechazados` | `desde`, `hasta` | Conteo por resultado y últimos 50 intentos. |
| `GET /reportes/exportar` | `tipo` (ventas, ocupacion, ranking, validaciones), `desde`, `hasta` | CSV `sivec_<tipo>_<fecha>.csv`, UTF-8 con BOM, separador `;`. |

### Exportación CSV

UTF-8 con BOM y separador `;` para que Excel en español lo abra bien. Las celdas de
texto que empiezan por `=`, `+`, `-` o `@` se prefijan con una comilla simple para
evitar inyección de fórmulas.
