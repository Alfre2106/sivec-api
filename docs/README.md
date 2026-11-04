# Documentación de SIVEC API

Instalación, ejecución y solución de problemas: [README.md](../README.md) (en la raíz del proyecto).

| Documento | Para qué sirve |
|---|---|
| [API.md](API.md) | Referencia de **todos los endpoints**: método, ruta, rol, cuerpo y respuesta de ejemplo, y errores posibles. Es el documento para conectar el frontend. |
| [ROLES.md](ROLES.md) | Matriz de endpoints y roles. **Generada** desde el código: `python -m scripts.generar_roles`. |
| [MODELO_DATOS.md](MODELO_DATOS.md) | Las 11 tablas, enumeraciones, índices y el diagrama entidad-relación (Mermaid). |
| [RESPALDO.md](RESPALDO.md) | Respaldo con `pg_dump`, restauración con `pg_restore` y cómo programarlos en Windows. |
| [postman/](postman) | Colección `SIVEC.postman_collection.json` y entorno `SIVEC.postman_environment.json`. **Generados** con `python -m scripts.generar_postman`. |

## Mantener la documentación al día

- **Roles**: no se edita a mano. Cambia `@rol_requerido(...)` en el código y ejecuta `python -m scripts.generar_roles`.
- **Postman**: la prueba `tests/test_postman.py` falla si la colección tiene un request que no existe en la API, si falta un
  endpoint o si usa una variable que no está en el entorno. Para actualizarla, edita `scripts/generar_postman.py` y vuelve a generarla.
- **Modelo de datos**: si cambias un modelo, crea la migración (`flask --app run db migrate`) y actualiza `MODELO_DATOS.md`.
- **API**: al agregar o cambiar un endpoint, actualiza `API.md`. La prueba `tests/test_roles.py` falla si una ruta privada
  queda sin decorador de rol, y `tests/test_robustez.py` si algún dato inválido produce un error 500.
