<#
.SYNOPSIS
    Restaura un respaldo de SIVEC en una base DISTINTA y muestra el conteo de filas.

.DESCRIPTION
    Crea la base destino (por defecto sivec_restore), restaura el respaldo con
    pg_restore y cuenta las filas de las tablas principales para demostrar que la
    restauracion funciona. NUNCA restaura sobre la base de trabajo.

.PARAMETER Archivo
    Respaldo (.dump) a restaurar. Por defecto, el mas reciente de backups\.

.PARAMETER BaseDestino
    Nombre de la base donde se restaura (por defecto sivec_restore).

.PARAMETER Reemplazar
    Si la base destino ya existe, la elimina y la vuelve a crear. Sin este
    parametro, el script se detiene para no pisar datos.

.PARAMETER Directorio
    Carpeta donde buscar el respaldo mas reciente (por defecto backups\).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\restore.ps1
    powershell -ExecutionPolicy Bypass -File .\scripts\restore.ps1 -Archivo .\backups\sivec_20261103_0200.dump -Reemplazar
#>
param(
    [string]$Archivo,
    [string]$BaseDestino = "sivec_restore",
    [switch]$Reemplazar,
    [string]$Directorio
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_comun.ps1")

$conexion = Get-ConexionSivec
$pgRestore = Find-HerramientaPostgres "pg_restore"
$psql = Find-HerramientaPostgres "psql"

# --- Validaciones de seguridad ---
if ($BaseDestino -notmatch '^[a-z][a-z0-9_]*$') {
    throw "Nombre de base no valido: '$BaseDestino' (usa minusculas, numeros y guion bajo)."
}
if ($BaseDestino -eq $conexion.Base) {
    throw "No se permite restaurar sobre la base de trabajo '$($conexion.Base)'. Usa otra, por ejemplo sivec_restore."
}

# --- Elegir el respaldo ---
if (-not $Archivo) {
    $carpeta = Get-DirectorioRespaldos $Directorio
    $ultimo = Get-ChildItem $carpeta -Filter "sivec_*.dump" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $ultimo) { throw "No hay respaldos en $carpeta. Ejecuta primero scripts\backup.ps1." }
    $Archivo = $ultimo.FullName
}
if (-not (Test-Path $Archivo)) { throw "No existe el respaldo: $Archivo" }

function Invoke-Psql {
    param([string]$Base, [string]$Sentencia)
    $salida = & $psql -X -q -h $conexion.Host -p $conexion.Puerto -U $conexion.Usuario -w `
        -d $Base -tA -c $Sentencia
    if ($LASTEXITCODE -ne 0) { throw "psql fallo ejecutando: $Sentencia" }
    return ($salida | Out-String).Trim()
}

$env:PGPASSWORD = $conexion.Clave
try {
    # --- Preparar la base destino ---
    $existe = Invoke-Psql "postgres" "SELECT 1 FROM pg_database WHERE datname = '$BaseDestino'"
    if ($existe -eq "1") {
        if (-not $Reemplazar) {
            throw "La base '$BaseDestino' ya existe. Usa -Reemplazar para eliminarla y restaurar de nuevo."
        }
        Write-Host "Eliminando la base existente '$BaseDestino'..."
        Invoke-Psql "postgres" "DROP DATABASE $BaseDestino WITH (FORCE)" | Out-Null
    }
    Write-Host "Creando la base '$BaseDestino'..."
    Invoke-Psql "postgres" "CREATE DATABASE $BaseDestino" | Out-Null

    # --- Restaurar ---
    Write-Host "Restaurando $(Split-Path $Archivo -Leaf) en '$BaseDestino'..."
    & $pgRestore -h $conexion.Host -p $conexion.Puerto -U $conexion.Usuario -w `
        --no-owner --no-privileges -d $BaseDestino $Archivo
    if ($LASTEXITCODE -ne 0) { throw "pg_restore fallo (codigo $LASTEXITCODE)." }

    # --- Demostrar que funciona: conteo de filas de las tablas principales ---
    $tablas = "usuarios", "clientes", "peliculas", "salas", "funciones", "asientos_funcion",
              "reservas", "compras", "entradas", "validaciones", "auditoria"
    $resumen = foreach ($tabla in $tablas) {
        [pscustomobject]@{
            Tabla                  = $tabla
            "Restaurada"           = [int](Invoke-Psql $BaseDestino "SELECT count(*) FROM $tabla")
            "Base de trabajo (hoy)" = [int](Invoke-Psql $conexion.Base "SELECT count(*) FROM $tabla")
        }
    }
    Write-Host ""
    Write-Host "Filas por tabla en '$BaseDestino':"
    $resumen | Format-Table -AutoSize | Out-String | Write-Host
    $total = ($resumen | Measure-Object -Property "Restaurada" -Sum).Sum
    Write-Host "Restauracion correcta: $total filas en $($tablas.Count) tablas."
    Write-Host "(Las dos columnas pueden diferir si hubo cambios despues del respaldo.)"
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}
