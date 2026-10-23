# Funciones compartidas por install.ps1 y start.ps1 (Windows PowerShell 5.1 o superior).
# Las rutas se calculan solas a partir de la ubicacion del proyecto: nunca escritas a mano.

$script:Raiz = Split-Path -Parent $PSScriptRoot
$script:Backend = Join-Path $script:Raiz 'backend'
$script:Frontend = Join-Path $script:Raiz 'frontend'
$script:DirRun = Join-Path $script:Raiz '.run'
$script:DirLogs = Join-Path $script:Raiz 'logs'
$script:ArchivoEnv = Join-Path $script:Backend '.env'
$script:ArchivoEnvWeb = Join-Path $script:Frontend '.env.local'
$script:PythonVenv = Join-Path $script:Backend 'venv\Scripts\python.exe'

function Escribir-Titulo([string]$Texto) {
    Write-Host ''
    Write-Host "==> $Texto" -ForegroundColor Magenta
}

function Escribir-Ok([string]$Texto) { Write-Host "    [ok] $Texto" -ForegroundColor Green }
function Escribir-Aviso([string]$Texto) { Write-Host "    [!] $Texto" -ForegroundColor Yellow }
function Escribir-Error([string]$Texto) { Write-Host "    [x] $Texto" -ForegroundColor Red }

function Preguntar-SiNo([string]$Pregunta, [bool]$PorDefecto = $false) {
    $sufijo = if ($PorDefecto) { '(S/n)' } else { '(s/N)' }
    $respuesta = Read-Host "$Pregunta $sufijo"
    if ([string]::IsNullOrWhiteSpace($respuesta)) { return $PorDefecto }
    return $respuesta.Trim().ToLower().StartsWith('s')
}

function Leer-Env([string]$Clave, [string]$PorDefecto = '') {
    if (-not (Test-Path $script:ArchivoEnv)) { return $PorDefecto }
    foreach ($linea in Get-Content -Path $script:ArchivoEnv -Encoding UTF8) {
        if ($linea -match "^\s*$([regex]::Escape($Clave))\s*=(.*)$") {
            $valor = $Matches[1].Trim()
            if ($valor) { return $valor }
            return $PorDefecto
        }
    }
    return $PorDefecto
}

function Escribir-Env([string]$Clave, [string]$Valor) {
    $lineas = @()
    if (Test-Path $script:ArchivoEnv) { $lineas = @(Get-Content -Path $script:ArchivoEnv -Encoding UTF8) }
    $encontrada = $false
    $nuevas = foreach ($linea in $lineas) {
        if ($linea -match "^\s*$([regex]::Escape($Clave))\s*=") { $encontrada = $true; "$Clave=$Valor" } else { $linea }
    }
    if (-not $encontrada) { $nuevas = @($nuevas) + "$Clave=$Valor" }
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($script:ArchivoEnv, [string[]]$nuevas, $utf8)
}

function Escribir-EnvWeb([int]$PuertoApi) {
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($script:ArchivoEnvWeb, "VITE_API_PUERTO=$PuertoApi`r`n", $utf8)
}

function Leer-Pid([string]$Nombre) {
    $archivo = Join-Path $script:DirRun "$Nombre.pid"
    if (-not (Test-Path $archivo)) { return $null }
    $texto = (Get-Content $archivo -Raw).Trim()
    if ($texto -match '^\d+$') { return [int]$texto }
    return $null
}

function Proceso-Vivo($IdProceso) {
    if (-not $IdProceso) { return $false }
    return [bool](Get-Process -Id $IdProceso -ErrorAction SilentlyContinue)
}

function Pids-Nuestros {
    $lista = @()
    foreach ($n in @('backend', 'frontend')) {
        $p = Leer-Pid $n
        if (Proceso-Vivo $p) { $lista += $p }
    }
    return $lista
}

function Es-Descendiente([int]$IdProceso, [int[]]$Raices) {
    # Sube por la cadena de procesos padre (runserver y npm encadenan 3-4 niveles).
    $actual = $IdProceso
    for ($i = 0; $i -lt 8 -and $actual; $i++) {
        if ($Raices -contains $actual) { return $true }
        $info = Get-CimInstance Win32_Process -Filter "ProcessId = $actual" -ErrorAction SilentlyContinue
        if (-not $info) { return $false }
        $actual = [int]$info.ParentProcessId
    }
    return $false
}

function Dueno-Puerto([int]$Puerto) {
    # Devuelve el PID que escucha en el puerto, o $null si esta libre.
    $conexion = Get-NetTCPConnection -LocalPort $Puerto -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conexion) { return [int]$conexion.OwningProcess }
    $escucha = $null
    try {
        $escucha = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Any, $Puerto)
        $escucha.Start()
        return $null
    } catch {
        return -1  # ocupado, sin poder identificar el proceso
    } finally {
        if ($escucha) { $escucha.Stop() }
    }
}

function Puerto-Ajeno([int]$Puerto) {
    $dueno = Dueno-Puerto $Puerto
    if ($null -eq $dueno) { return $false }
    $nuestros = Pids-Nuestros
    if ($dueno -gt 0 -and $nuestros.Count -gt 0 -and (Es-Descendiente $dueno $nuestros)) { return $false }
    return $true
}

function Describir-Puerto([int]$Puerto) {
    $dueno = Dueno-Puerto $Puerto
    if ($dueno -gt 0) {
        $proceso = Get-Process -Id $dueno -ErrorAction SilentlyContinue
        if ($proceso) { return "PID $dueno ($($proceso.ProcessName))" }
        return "PID $dueno"
    }
    return 'un proceso no identificado'
}

function Buscar-PuertoLibre([int]$Desde, [int[]]$Evitar = @()) {
    for ($p = $Desde; $p -lt $Desde + 200; $p++) {
        if ($Evitar -contains $p) { continue }
        if ($null -eq (Dueno-Puerto $p)) { return $p }
    }
    throw "No se encontro un puerto libre a partir de $Desde."
}

function Asegurar-Puertos {
    # Usa los puertos guardados en .env; si alguno esta ocupado por algo ajeno, NO lo toca:
    # busca el siguiente libre, lo guarda y avisa. Devuelve $true si el puerto de la API cambio.
    $api = [int](Leer-Env 'PUERTO_API' '9006')
    $web = [int](Leer-Env 'PUERTO_WEB' '5206')
    $apiAnterior = $api
    if (Puerto-Ajeno $api) {
        $nuevo = Buscar-PuertoLibre ($api + 1) @($web)
        Escribir-Aviso "El puerto $api esta ocupado por $(Describir-Puerto $api). No interfiero: la API usara el $nuevo."
        $api = $nuevo
    }
    if (Puerto-Ajeno $web) {
        $nuevo = Buscar-PuertoLibre ($web + 1) @($api)
        Escribir-Aviso "El puerto $web esta ocupado por $(Describir-Puerto $web). No interfiero: la web usara el $nuevo."
        $web = $nuevo
    }
    Escribir-Env 'PUERTO_API' $api
    Escribir-Env 'PUERTO_WEB' $web
    Escribir-EnvWeb $api
    $script:PuertoApi = $api
    $script:PuertoWeb = $web
    return ($api -ne $apiAnterior)
}

function Ip-Local {
    $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
        Select-Object -First 1
    if ($ip) { return $ip.IPAddress }
    return $null
}

function Ejecutar-Manage([string[]]$Argumentos) {
    Push-Location $script:Backend
    try {
        & $script:PythonVenv manage.py @Argumentos
        if ($LASTEXITCODE -ne 0) { throw "Fallo: manage.py $($Argumentos -join ' ')" }
    } finally { Pop-Location }
}

function Ejecutar-Npm([string[]]$Argumentos) {
    Push-Location $script:Frontend
    try {
        & npm.cmd @Argumentos
        if ($LASTEXITCODE -ne 0) { throw "Fallo: npm $($Argumentos -join ' ')" }
    } finally { Pop-Location }
}

function Generar-MigracionesFaltantes {
    # Genera las migraciones que falten (app nueva o modelo cambiado). Si no hay cambios no hace nada.
    # --noinput: nunca se queda esperando una respuesta (si algo requiere decisión, falla y se ve en pantalla).
    $apps = @('plataforma', 'identidad', 'auditoria', 'territorio', 'padron', 'facturacion', 'recorridos', 'lecturas', 'tarifas', 'migracion_bd', 'respaldo', 'manual')
    Ejecutar-Manage (@('makemigrations', '--noinput') + $apps)
}
