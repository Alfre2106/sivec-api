# Funciones compartidas por backup.ps1 y restore.ps1.
# Este archivo NO se ejecuta solo; los otros scripts lo cargan con ". .\_comun.ps1".
#
# Seguridad: la contraseña de la base NUNCA está escrita en los scripts. Se lee
# del archivo .env en el momento de ejecutar y solo se deja en la variable de
# entorno PGPASSWORD de esta sesión (se borra al terminar).

function Get-RaizProyecto {
    # La carpeta scripts\ está dentro de la raíz del proyecto.
    return Split-Path -Parent $PSScriptRoot
}

function Get-ConexionSivec {
    <#
    Lee DATABASE_URL del .env y devuelve host, puerto, usuario, clave y base.
    Formato esperado: postgresql+psycopg2://usuario:clave@host:puerto/base
    #>
    $archivoEnv = Join-Path (Get-RaizProyecto) ".env"
    if (-not (Test-Path $archivoEnv)) {
        throw "No se encontro el archivo .env en $(Get-RaizProyecto). Copia .env.example como .env y completa DATABASE_URL."
    }

    $linea = Get-Content $archivoEnv -Encoding UTF8 |
        Where-Object { $_ -match '^\s*DATABASE_URL\s*=' } | Select-Object -First 1
    if (-not $linea) { throw "El .env no define DATABASE_URL." }

    $url = ($linea -replace '^\s*DATABASE_URL\s*=\s*', '').Trim().Trim('"').Trim("'")
    $patron = '^[\w+]+://(?<usuario>[^:/@]+)(:(?<clave>.*))?@(?<host>[^:/@]+)(:(?<puerto>\d+))?/(?<base>[^?\s]+)'
    if ($url -notmatch $patron) {
        throw "DATABASE_URL no tiene el formato esperado (postgresql+psycopg2://usuario:clave@host:puerto/base)."
    }

    $puerto = if ($Matches.puerto) { $Matches.puerto } else { "5432" }
    return [pscustomobject]@{
        Host    = $Matches.host
        Puerto  = $puerto
        Usuario = [System.Uri]::UnescapeDataString($Matches.usuario)
        Clave   = [System.Uri]::UnescapeDataString($Matches.clave)
        Base    = $Matches.base
    }
}

function Find-HerramientaPostgres {
    <#
    Busca un ejecutable de PostgreSQL (pg_dump, pg_restore, psql): primero en el
    PATH y, si no esta, en C:\Program Files\PostgreSQL\<version>\bin (la version mas nueva).
    #>
    param([Parameter(Mandatory)][string]$Nombre)

    $enPath = Get-Command $Nombre -ErrorAction SilentlyContinue
    if ($enPath) { return $enPath.Source }

    $candidatos = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\$Nombre.exe" -ErrorAction SilentlyContinue |
        Sort-Object { [int]($_.Directory.Parent.Name -replace '\D', '') } -Descending
    if ($candidatos) { return $candidatos[0].FullName }

    throw "No se encontro $Nombre.exe en el PATH ni en C:\Program Files\PostgreSQL\*\bin. Instala PostgreSQL o agrega su carpeta bin al PATH."
}

function Get-DirectorioRespaldos {
    param([string]$Directorio)
    if ($Directorio) { return $Directorio }
    return Join-Path (Get-RaizProyecto) "backups"
}
