# Respaldo y restauración de la base de datos (RNF-05)

Dos scripts de PowerShell en `scripts\`:

| Script | Qué hace |
|---|---|
| `backup.ps1` | Respaldo con `pg_dump` en formato custom (`-Fc`): `backups\sivec_AAAAMMDD_HHmm.dump`. Verifica que el archivo se pueda leer y conserva solo los **últimos 14**. |
| `restore.ps1` | Restaura un respaldo en una base **distinta** (por defecto `sivec_restore`) con `pg_restore` y muestra el conteo de filas de las 11 tablas. |
| `_comun.ps1` | Funciones compartidas (lee el `.env`, busca `pg_dump`/`psql`). No se ejecuta solo. |

Cómo funcionan por dentro:

- Buscan `pg_dump`, `pg_restore` y `psql` en el `PATH` y, si no están, en
  `C:\Program Files\PostgreSQL\<versión>\bin` (la versión más nueva).
- **La contraseña no está escrita en ningún script.** Se lee del `DATABASE_URL` del `.env` al
  ejecutar y se deja solo en `PGPASSWORD` de esa sesión, que se borra al terminar.
- Se ejecutan desde la raíz del proyecto (`sivec-api`).
- `backups\` está en el `.gitignore`: los respaldos contienen datos de clientes y **no deben subirse al repositorio**.

## Hacer un respaldo

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1
```

Salida esperada:

```
Respaldando la base 'sivec' en localhost:5432...
Respaldo creado: C:\...\sivec-api\backups\sivec_20261103_0200.dump (65 KB, 146 objetos). Respaldos conservados: 1.
```

Opciones:

```powershell
# Otra carpeta (por ejemplo un disco externo o una carpeta sincronizada)
powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1 -Directorio "D:\Respaldos\SIVEC"

# Conservar los últimos 30 en vez de 14
powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1 -Retener 30
```

Si algo falla (base inaccesible, `pg_dump` no encontrado), el script termina con error, **no deja un archivo a medias**
y no borra respaldos anteriores.

## Restaurar y comprobar

Restaura el respaldo más reciente en `sivec_restore` y muestra el conteo de filas:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore.ps1
```

```
Creando la base 'sivec_restore'...
Restaurando sivec_20261103_0200.dump en 'sivec_restore'...

Filas por tabla en 'sivec_restore':
Tabla            Restaurada Base de trabajo (hoy)
-----            ---------- ---------------------
usuarios                  3                     3
clientes                  2                     2
peliculas                 7                     7
salas                     2                     2
funciones                58                    58
asientos_funcion       4408                  4408
reservas                 13                    13
compras                   8                     8
entradas                 16                    16
validaciones              0                     0
auditoria                66                    66
Restauracion correcta: 4583 filas en 11 tablas.
```

Si hubo movimiento después del respaldo, la columna «Base de trabajo (hoy)» tendrá valores mayores: es lo esperado.

Opciones:

```powershell
# Un respaldo concreto
powershell -ExecutionPolicy Bypass -File .\scripts\restore.ps1 -Archivo .\backups\sivec_20261103_0200.dump

# Otra base destino (solo minúsculas, números y guion bajo)
powershell -ExecutionPolicy Bypass -File .\scripts\restore.ps1 -BaseDestino sivec_prueba

# Si la base destino ya existe: eliminarla y restaurar de nuevo
powershell -ExecutionPolicy Bypass -File .\scripts\restore.ps1 -Reemplazar
```

Protecciones: el script **se niega a restaurar sobre la base de trabajo** (`sivec`), y si la base destino ya existe se detiene
a menos que uses `-Reemplazar`.

Para dejar de usar la base restaurada:

```powershell
psql -U postgres -c "DROP DATABASE sivec_restore;"
```

### Recuperarse de un desastre real

El script de restauración sirve para **comprobar** que los respaldos funcionan. Para recuperar la base de producción tras
perderla:

1. Detén la API.
2. Restaura en una base temporal con `restore.ps1` y revisa que los datos sean los esperados.
3. Si todo está bien, reemplaza la base de trabajo manualmente (por ejemplo con `pg_restore --clean --if-exists -d sivec
   archivo.dump`) o renombra `sivec_restore` a `sivec` y apunta el `DATABASE_URL` a ella.

## Programar el respaldo diario (Programador de tareas de Windows)

Ejemplo: todos los días a las 2:00 a. m. Ejecútalo en el **Símbolo del sistema (cmd)**, cambiando la ruta por la de tu
proyecto:

```bat
schtasks /Create /TN "SIVEC Respaldo Diario" /SC DAILY /ST 02:00 /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"C:\Users\TU_USUARIO\sivec-api\scripts\backup.ps1\"" /F
```

Notas sobre el comando:

- `/TN` es el nombre de la tarea, `/SC DAILY /ST 02:00` la repite a diario a esa hora y `/F` la sobrescribe si ya existe.
- Las comillas escapadas (`\"`) alrededor de la ruta permiten rutas con espacios.
- Por defecto la tarea corre con **tu usuario** y solo cuando tienes la sesión iniciada. Si el equipo debe respaldar sin
  sesión abierta, añade `/RU "TU_USUARIO" /RP *` (te pedirá la contraseña de Windows una vez) o usa la interfaz gráfica.
- El equipo debe estar encendido a esa hora. En el Programador de tareas (interfaz gráfica) puedes marcar «Ejecutar la tarea
  lo antes posible después de una ejecución programada omitida».

Comandos útiles:

```bat
:: Ejecutarla ahora mismo para probar
schtasks /Run /TN "SIVEC Respaldo Diario"

:: Ver su estado (busca «Último resultado»: 0 = correcto)
schtasks /Query /TN "SIVEC Respaldo Diario" /V /FO LIST

:: Eliminarla
schtasks /Delete /TN "SIVEC Respaldo Diario" /F
```

Para guardar un registro de cada ejecución, cambia la acción por:

```bat
schtasks /Create /TN "SIVEC Respaldo Diario" /SC DAILY /ST 02:00 /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \"& 'C:\Users\TU_USUARIO\sivec-api\scripts\backup.ps1' *>> 'C:\Users\TU_USUARIO\sivec-api\backups\respaldo.log'\"" /F
```

## Buenas prácticas

- **Copia los respaldos fuera del equipo** (disco externo, otra máquina o carpeta sincronizada): un respaldo que solo existe en el
  mismo disco no protege contra una falla del disco. Usa `-Directorio` para guardarlos allí directamente.
- **Prueba la restauración de vez en cuando** (`restore.ps1`). Un respaldo que nunca se restauró no está comprobado.
- Los respaldos incluyen todos los datos, también los de clientes y el historial de auditoría: protégelos igual que la base.
- Los respaldos no contienen la contraseña del usuario de PostgreSQL ni el `.env`; guarda el `.env` (sin subirlo a git) por separado.

## Solución de problemas

| Síntoma | Causa y solución |
|---|---|
| `no se puede cargar el archivo ... la ejecución de scripts está deshabilitada` | Usa `powershell -ExecutionPolicy Bypass -File ...` como en los ejemplos, o `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |
| `No se encontro pg_dump.exe` | Instala PostgreSQL o agrega `C:\Program Files\PostgreSQL\17\bin` al `PATH`. |
| `password authentication failed` | La contraseña del `DATABASE_URL` en el `.env` es incorrecta. Si tiene `@`, `:` o `/`, escríbela codificada (`@` → `%40`). |
| `El .env no define DATABASE_URL` | Ejecuta el script desde la raíz del proyecto y revisa que exista `.env` (copia de `.env.example`). |
| `La base 'sivec_restore' ya existe` | Usa `-Reemplazar`, o elige otra con `-BaseDestino`. |
| `server version mismatch` de `pg_dump` | El `pg_dump` del `PATH` es más antiguo que el servidor. El script usa el del `PATH` primero; pon delante la carpeta `bin` de la versión más nueva. |
