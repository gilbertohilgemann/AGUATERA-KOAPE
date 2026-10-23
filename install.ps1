# Instalador de Koape Aguateras para Windows.
# Se corre una vez (o de nuevo al actualizar el código). Es idempotente.
# Uso: doble clic en install.bat, o en PowerShell: .\install.ps1
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\comun.ps1')

Write-Host ''
Write-Host '  KOAPE SISTEMAS EAS · Aguateras' -ForegroundColor Magenta
Write-Host '  Instalador para Windows' -ForegroundColor Gray

# --- 1. Dependencias del sistema -------------------------------------------------------
Escribir-Titulo 'Revisando dependencias del sistema'

function Buscar-Python {
    # Deja en $script:PyExe / $script:PyArgs el primer Python 3.10+ disponible.
    foreach ($candidato in @('py -3', 'python')) {
        $partes = $candidato.Split(' ')
        $exe = $partes[0]
        $extra = @($partes | Select-Object -Skip 1)
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $version = & $exe @extra -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $version) {
            $numeros = "$version".Trim().Split('.')
            if ([int]$numeros[0] -eq 3 -and [int]$numeros[1] -ge 10) {
                $script:PyExe = $exe
                $script:PyArgs = $extra
                return $true
            }
        }
    }
    return $false
}

if (-not (Buscar-Python)) {
    Escribir-Aviso 'No se encontró Python 3.10 o superior.'
    if ((Get-Command winget -ErrorAction SilentlyContinue) -and (Preguntar-SiNo '¿Instalar Python 3.12 con winget?')) {
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        Escribir-Aviso 'Python instalado. Cierre esta ventana y vuelva a ejecutar install.bat (para que tome el PATH nuevo).'
    } else {
        Escribir-Error 'Instale Python 3.10+ desde https://www.python.org/downloads/ (marcar "Add to PATH") y vuelva a ejecutar.'
    }
    exit 1
}
Escribir-Ok "Python: $(& $script:PyExe @($script:PyArgs) --version)"

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Escribir-Aviso 'No se encontró Node.js.'
    if ((Get-Command winget -ErrorAction SilentlyContinue) -and (Preguntar-SiNo '¿Instalar Node.js LTS con winget?')) {
        winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
        Escribir-Aviso 'Node.js instalado. Cierre esta ventana y vuelva a ejecutar install.bat.'
    } else {
        Escribir-Error 'Instale Node.js 20 LTS o superior desde https://nodejs.org/ y vuelva a ejecutar.'
    }
    exit 1
}
Escribir-Ok "Node.js: $(node --version)"

# Si el sistema ya está corriendo, se detiene para poder actualizar sin archivos bloqueados.
if ((Pids-Nuestros).Count -gt 0) {
    Escribir-Aviso 'El sistema está en marcha: se detiene para actualizar.'
    & (Join-Path $script:Raiz 'start.ps1') stop
}

# --- 2. Backend -----------------------------------------------------------------------------
Escribir-Titulo 'Preparando el backend (Django)'
if (-not (Test-Path $script:PythonVenv)) {
    & $script:PyExe @($script:PyArgs) -m venv (Join-Path $script:Backend 'venv')
    Escribir-Ok 'Entorno virtual creado (backend\venv).'
}
& $script:PythonVenv -m pip install --upgrade pip --quiet
& $script:PythonVenv -m pip install -r (Join-Path $script:Backend 'requirements.txt') --quiet
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias de Python.' }
Escribir-Ok 'Dependencias de Python instaladas.'

if (-not (Test-Path $script:ArchivoEnv)) {
    Copy-Item (Join-Path $script:Backend '.env.example') $script:ArchivoEnv
    Escribir-Ok 'Archivo backend\.env creado.'
}
if (-not (Leer-Env 'SECRET_KEY')) {
    $clave = & $script:PythonVenv -c "import secrets; print(secrets.token_urlsafe(50))"
    Escribir-Env 'SECRET_KEY' $clave.Trim()
    Escribir-Ok 'SECRET_KEY generada.'
}
if (-not (Leer-Env 'CLAVE_CIFRADO')) {
    # Igual a SECRET_KEY: es la clave que el sistema ya usa si falta, así nada guardado deja de leerse.
    Escribir-Env 'CLAVE_CIFRADO' (Leer-Env 'SECRET_KEY')
    Escribir-Ok 'CLAVE_CIFRADO configurada.'
}

# --- 3. Puertos --------------------------------------------------------------------------------
Escribir-Titulo 'Buscando puertos libres'
[void](Asegurar-Puertos)
Escribir-Ok "API: $($script:PuertoApi) · Web: $($script:PuertoWeb)"

# --- 4. Base de datos -----------------------------------------------------------------------
Escribir-Titulo 'Preparando la base de datos (SQLite por defecto)'
Generar-MigracionesFaltantes
Ejecutar-Manage @('migrate', '--noinput')
Ejecutar-Manage @('collectstatic', '--noinput', '--verbosity', '0')
Ejecutar-Manage @('asegurar_admin_plataforma')
Escribir-Ok 'Base de datos al día (SQLite).'
Escribir-Aviso 'PostgreSQL es opcional: se migra después, sin perder datos, desde el panel de la plataforma.'

if (Preguntar-SiNo '¿Crear las instituciones de DEMOSTRACIÓN (DEMO y DEMO2)?' $true) {
    Ejecutar-Manage @('crear_institucion_demo')
}

# --- 5. Frontend --------------------------------------------------------------------------
Escribir-Titulo 'Preparando el frontend (React)'
Ejecutar-Npm @('install', '--no-fund', '--no-audit')
if ((Leer-Env 'MODO' 'desarrollo') -eq 'produccion') {
    Ejecutar-Npm @('run', 'build')
    Escribir-Ok 'Build de producción generado.'
}
Escribir-Ok 'Dependencias del frontend instaladas.'

# --- 6. Resumen ----------------------------------------------------------------------------
$usuario = Leer-Env 'ADMIN_PLATAFORMA_USUARIO' 'admin'
$contrasena = Leer-Env 'ADMIN_PLATAFORMA_CONTRASENA'
$ip = Ip-Local
Escribir-Titulo 'Instalación terminada'
Write-Host "    Arrancar:            start.bat            (detener: start.bat stop · estado: start.bat status)"
Write-Host "    Sistema:             http://localhost:$($script:PuertoWeb)/"
if ($ip) { Write-Host "    Desde la red local:  http://$($ip):$($script:PuertoWeb)/" }
Write-Host "    Panel de plataforma: http://localhost:$($script:PuertoApi)/admin/"
Write-Host "    Usuario plataforma:  $usuario  /  $contrasena"
Write-Host "    Instituciones demo:  código DEMO o DEMO2 · usuario admin · contraseña Demo.Koape.2026"
Write-Host ''
Escribir-Aviso 'Cambie la contraseña del administrador de la plataforma apenas ingrese al panel.'
Escribir-Aviso 'El arranque automático con Windows no se configura: use start.bat (o el Programador de tareas).'
