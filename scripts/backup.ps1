<#
.SYNOPSIS
    Respaldo de la base de datos de SIVEC con pg_dump (RNF-05).

.DESCRIPTION
    Crea backups\sivec_AAAAMMDD_HHmm.dump en formato custom (-Fc), verifica que el
    archivo se pueda leer y conserva solo los ultimos N respaldos (14 por defecto).
    Los datos de conexion se leen del .env en tiempo de ejecucion; la contrasena
    no esta escrita en este script.

.PARAMETER Directorio
    Carpeta de destino. Por defecto, backups\ en la raiz del proyecto.

.PARAMETER Retener
    Cuantos respaldos conservar (por defecto 14).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1
#>
param(
    [string]$Directorio,
    [ValidateRange(1, 3650)][int]$Retener = 14
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_comun.ps1")

$conexion = Get-ConexionSivec
$pgDump = Find-HerramientaPostgres "pg_dump"
$pgRestore = Find-HerramientaPostgres "pg_restore"

$destino = Get-DirectorioRespaldos $Directorio
New-Item -ItemType Directory -Path $destino -Force | Out-Null

$marca = Get-Date -Format "yyyyMMdd_HHmm"
$archivo = Join-Path $destino "sivec_$marca.dump"
if (Test-Path $archivo) {
    # Dos respaldos en el mismo minuto: se distingue con los segundos.
    $archivo = Join-Path $destino ("sivec_{0}.dump" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
}

Write-Host "Respaldando la base '$($conexion.Base)' en $($conexion.Host):$($conexion.Puerto)..."
$env:PGPASSWORD = $conexion.Clave
try {
    # -Fc: formato custom (comprimido, restaurable con pg_restore). -w: nunca pedir contrasena.
    & $pgDump -h $conexion.Host -p $conexion.Puerto -U $conexion.Usuario -w -Fc -f $archivo $conexion.Base
    $codigo = $LASTEXITCODE
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

if ($codigo -ne 0) {
    if (Test-Path $archivo) { Remove-Item $archivo -Force }   # no dejar archivos a medias
    throw "pg_dump fallo (codigo $codigo). No se creo el respaldo."
}

# Verificacion: el indice del archivo debe poder leerse y no estar vacio.
$tamano = (Get-Item $archivo).Length
$elementos = (& $pgRestore -l $archivo | Measure-Object -Line).Lines
if ($tamano -le 0 -or $LASTEXITCODE -ne 0 -or $elementos -lt 10) {
    Remove-Item $archivo -Force
    throw "El respaldo generado no es valido (tamano $tamano bytes). Se elimino."
}

# Retencion: se borran los respaldos mas antiguos, dejando los ultimos $Retener.
$viejos = Get-ChildItem $destino -Filter "sivec_*.dump" | Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $Retener
foreach ($viejo in $viejos) {
    Remove-Item $viejo.FullName -Force
    Write-Host "  Eliminado respaldo antiguo: $($viejo.Name)"
}
$conservados = (Get-ChildItem $destino -Filter "sivec_*.dump").Count

Write-Host ("Respaldo creado: {0} ({1:N0} KB, {2} objetos). Respaldos conservados: {3}." -f `
    $archivo, ($tamano / 1KB), $elementos, $conservados)
