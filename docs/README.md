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
