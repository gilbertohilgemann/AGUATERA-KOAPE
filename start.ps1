# Arranque de Koape Aguateras en Windows.
# Uso: start.bat [start|stop|status|restart|logs|update|red|red-quitar|https|https-quitar|
#                  respaldo|respaldo-programar|respaldo-quitar|verificar <zip>|restaurar <zip>|seguridad|datos-prueba]
param(
    [ValidateSet('start', 'stop', 'status', 'restart', 'logs', 'update', 'red', 'red-quitar', 'https', 'https-quitar',
                 'respaldo', 'respaldo-programar', 'respaldo-quitar', 'verificar', 'restaurar', 'seguridad',
                 'datos-prueba')]
    [string]$Comando = 'start',
    [string]$Archivo = ''
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\comun.ps1')

New-Item -ItemType Directory -Force -Path $script:DirRun, $script:DirLogs | Out-Null

# Servidor web con HTTPS (Caddy). Versión fija y firma SHA-512 publicada por el proyecto: si la descarga
# no coincide, no se instala.
$script:CaddyVersion = '2.8.4'
$script:CaddySha512 = '89f8fc9ece9941a15a0981b3c69543d3b9b5fe095e747875a05fc1775d4d78d4505a7fe54a58d496dade601e85f6053a00a1b0382a781d3e8b6eec044384f6e6'
$script:Caddy = Join-Path $script:Raiz 'herramientas\caddy\caddy.exe'
$script:DirHttps = Join-Path $script:Raiz 'https'
$script:TareaRespaldo = 'Koape Aguateras - respaldo diario'

function Detener([string]$Nombre) {
    $idProceso = Leer-Pid $Nombre
    $archivo = Join-Path $script:DirRun "$Nombre.pid"
    if (Proceso-Vivo $idProceso) {
        # /T mata el árbol completo (runserver con autoreload y npm encadenan varios procesos hijos).
        & taskkill.exe /PID $idProceso /T /F | Out-Null
        Escribir-Ok "$Nombre detenido (PID $idProceso)."
    }
    Remove-Item $archivo -ErrorAction SilentlyContinue
}

function Lanzar([string]$Nombre, [string]$Ejecutable, [string]$Argumentos, [string]$Carpeta) {
    $salida = Join-Path $script:DirLogs "$Nombre.log"
    $errores = Join-Path $script:DirLogs "$Nombre.err.log"
    $proceso = Start-Process -FilePath $Ejecutable -ArgumentList $Argumentos -WorkingDirectory $Carpeta `
        -WindowStyle Hidden -RedirectStandardOutput $salida -RedirectStandardError $errores -PassThru
    Set-Content -Path (Join-Path $script:DirRun "$Nombre.pid") -Value $proceso.Id
    Escribir-Ok "$Nombre iniciado (PID $($proceso.Id))."
}

function Iniciar {
    if (-not (Test-Path $script:PythonVenv)) { Escribir-Error 'Falta instalar: ejecute install.bat primero.'; exit 1 }
    if ((Pids-Nuestros).Count -gt 0) { Escribir-Aviso 'El sistema ya está en marcha.'; Estado; return }

    $cambioApi = Asegurar-Puertos
    $modo = Leer-Env 'MODO' 'desarrollo'
    if ($modo -eq 'produccion' -and ($cambioApi -or -not (Test-Path (Join-Path $script:Frontend 'dist')))) {
        Escribir-Aviso 'Rearmando el frontend (cambió el puerto de la API o falta el build).'
        Ejecutar-Npm @('run', 'build')
    }

    if (Esta-Https) {
        # El backend queda solo para esta computadora: todo entra por el servidor web (HTTPS).
        Obtener-Caddy
        $config = Escribir-Caddyfile
        Lanzar 'backend' $script:PythonVenv "-m waitress --listen=127.0.0.1:$($script:PuertoApi) configuracion.wsgi:application" $script:Backend
        Lanzar 'frontend' $script:Caddy "run --config `"$config`" --adapter caddyfile" $script:Raiz
    } elseif ($modo -eq 'produccion') {
        Lanzar 'backend' $script:PythonVenv "-m waitress --listen=0.0.0.0:$($script:PuertoApi) configuracion.wsgi:application" $script:Backend
        Lanzar 'frontend' 'cmd.exe' "/c npm run preview -- --port $($script:PuertoWeb) --strictPort" $script:Frontend
    } else {
        Lanzar 'backend' $script:PythonVenv "manage.py runserver 0.0.0.0:$($script:PuertoApi)" $script:Backend
        Lanzar 'frontend' 'cmd.exe' "/c npm run dev -- --port $($script:PuertoWeb) --strictPort" $script:Frontend
    }
    Start-Sleep -Seconds 3
    Estado
}

function Estado {
    $api = Leer-Env 'PUERTO_API' '9006'
    $web = Leer-Env 'PUERTO_WEB' '5206'
    foreach ($n in @('backend', 'frontend')) {
        $p = Leer-Pid $n
        if (Proceso-Vivo $p) { Escribir-Ok "$n en marcha (PID $p)" } else { Escribir-Aviso "$n detenido" }
    }
    $ip = Ip-Local
    if (Esta-Https) {
        $base = "https://localhost$(Sufijo-Https)"
        Write-Host "    Sistema:             $base/"
        if ($ip) { Write-Host "    Desde la red local:  https://$ip$(Sufijo-Https)/" }
        Write-Host "    Panel de plataforma: $base/admin/"
        Write-Host "    Certificado:         http://$(if ($ip) { $ip } else { 'localhost' }):$web/certificado.crt"
    } else {
        Write-Host "    Sistema:             http://localhost:$web/"
        if ($ip) { Write-Host "    Desde la red local:  http://$($ip):$web/" }
        Write-Host "    Panel de plataforma: http://localhost:$api/admin/"
    }
    Write-Host "    Logs:                $($script:DirLogs)"
}

function Ver-Logs {
    foreach ($archivo in Get-ChildItem $script:DirLogs -Filter '*.log' -ErrorAction SilentlyContinue) {
        Escribir-Titulo $archivo.Name
        Get-Content $archivo.FullName -Tail 40
    }
}

function Actualizar {
    # Desplegar una versión nueva: sobrescribir archivos nunca alcanza.
    Detener 'frontend'; Detener 'backend'
    & $script:PythonVenv -m pip install -r (Join-Path $script:Backend 'requirements.txt') --quiet
    Generar-MigracionesFaltantes
    Ejecutar-Manage @('migrate', '--noinput')
    Ejecutar-Manage @('collectstatic', '--noinput', '--verbosity', '0')
    Ejecutar-Npm @('install', '--no-fund', '--no-audit')
    if ((Leer-Env 'MODO' 'desarrollo') -eq 'produccion') { Ejecutar-Npm @('run', 'build') }
    Iniciar
}

function Es-Administrador {
    $actual = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    return $actual.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Habilitar-Red([bool]$Quitar = $false) {
    # Abre (o cierra) los puertos del sistema en el Firewall de Windows SOLO para equipos de la misma
    # red local (RemoteAddress LocalSubnet): desde Internet sigue cerrado. Necesita permisos de administrador.
    if (-not (Es-Administrador)) {
        Escribir-Aviso 'Hace falta permiso de administrador: Windows va a pedir confirmación.'
        $accion = if ($Quitar) { 'red-quitar' } else { 'red' }
        Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait `
            -ArgumentList "-NoProfile -ExecutionPolicy Bypass -NoExit -File `"$PSCommandPath`" $accion"
        return
    }
    $api = [int](Leer-Env 'PUERTO_API' '9006')
    $web = [int](Leer-Env 'PUERTO_WEB' '5206')
    foreach ($nombre in @('Koape Aguateras (API)', 'Koape Aguateras (Web)', 'Koape Aguateras (HTTPS)')) {
        Get-NetFirewallRule -DisplayName $nombre -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    }
    if ($Quitar) { Escribir-Ok 'Acceso desde la red local cerrado (solo esta computadora).'; return }
    New-NetFirewallRule -DisplayName 'Koape Aguateras (Web)' -Direction Inbound -Protocol TCP -LocalPort $web `
        -Action Allow -Profile Any -RemoteAddress LocalSubnet | Out-Null
    if (Esta-Https) {
        # Con HTTPS el backend no se expone: entra todo por el puerto HTTPS (el $web solo redirige y entrega el certificado).
        $https = [int](Leer-Env 'PUERTO_HTTPS' '443')
        New-NetFirewallRule -DisplayName 'Koape Aguateras (HTTPS)' -Direction Inbound -Protocol TCP -LocalPort $https `
            -Action Allow -Profile Any -RemoteAddress LocalSubnet | Out-Null
        Escribir-Ok "Firewall: puertos $https (HTTPS) y $web (redirección y certificado) abiertos solo para la red local."
    } else {
        New-NetFirewallRule -DisplayName 'Koape Aguateras (API)' -Direction Inbound -Protocol TCP -LocalPort $api `
            -Action Allow -Profile Any -RemoteAddress LocalSubnet | Out-Null
        Escribir-Ok "Firewall: puertos $web (sistema) y $api (servidor) abiertos solo para equipos de la red local."
    }

    $ip = Ip-Local
    if (Esta-Https) {
        Agregar-OrigenesHttps
        Escribir-Ok 'Orígenes HTTPS actualizados con la IP de esta computadora (reinicie con start.bat restart).'
        if ($ip) { Write-Host "    Desde otras computadoras o celulares de la red:  https://$ip$(Sufijo-Https)/" }
        Write-Host '    Si la IP cambia (DHCP), conviene fijarla en el router para esta computadora.'
        return
    }
    if ((Leer-Env 'DEBUG' 'True') -notin @('True', 'true', '1')) {
        # Producción: el servidor solo atiende los nombres/orígenes declarados.
        $hosts = @('localhost', '127.0.0.1') + @($ip | Where-Object { $_ })
        $origenes = $hosts | ForEach-Object { "http://$($_):$web" }
        foreach ($par in @(@('ALLOWED_HOSTS', $hosts), @('CORS_ALLOWED_ORIGINS', $origenes), @('CSRF_TRUSTED_ORIGINS', $origenes))) {
            $previos = @((Leer-Env $par[0] '') -split ',' | Where-Object { $_ })
            $valor = (@($par[1]) + $previos | Select-Object -Unique) -join ','
            Escribir-Env $par[0] $valor
        }
        Escribir-Ok 'Configuración de producción: se agregó la IP de esta computadora a los orígenes permitidos (reinicie con start.bat restart).'
    }
    if ($ip) { Write-Host "    Desde otras computadoras o celulares de la red:  http://$($ip):$web/" }
    Write-Host '    Si la IP cambia (DHCP), conviene fijarla en el router para esta computadora.'
}

# --- HTTPS ---------------------------------------------------------------------------------------------
function Esta-Https { return (Leer-Env 'HTTPS' 'False') -in @('True', 'true', '1') }

function Sufijo-Https {
    $https = [int](Leer-Env 'PUERTO_HTTPS' '443')
    if ($https -eq 443) { return '' }
    return ":$https"
}

function Ips-Locales {
    return @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
        ForEach-Object { $_.IPAddress })
}

function Nombres-Servidor {
    return @(@('localhost', '127.0.0.1', $env:COMPUTERNAME.ToLower()) + (Ips-Locales) | Where-Object { $_ } | Select-Object -Unique)
}

function Obtener-Caddy {
    if (Test-Path $script:Caddy) { return }
    $v = $script:CaddyVersion
    Escribir-Titulo "Descargando el servidor HTTPS (Caddy $v)"
    $zip = Join-Path $env:TEMP "caddy_$v.zip"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -OutFile $zip `
        -Uri "https://github.com/caddyserver/caddy/releases/download/v$v/caddy_$($v)_windows_amd64.zip"
    $hash = (Get-FileHash -Algorithm SHA512 -Path $zip).Hash.ToLower()
    if ($hash -ne $script:CaddySha512) {
        Remove-Item $zip -ErrorAction SilentlyContinue
        throw 'La descarga de Caddy no coincide con la firma publicada: no se instala.'
    }
    $carpeta = Split-Path $script:Caddy
    New-Item -ItemType Directory -Force -Path $carpeta | Out-Null
    Expand-Archive -Path $zip -DestinationPath $carpeta -Force
    Remove-Item $zip -ErrorAction SilentlyContinue
    Escribir-Ok "Caddy $v instalado (firma verificada)."
}

function Escribir-Caddyfile {
    # Se rehace en cada arranque: si cambió la IP, el certificado nuevo sale de la misma autoridad local.
    $https = [int](Leer-Env 'PUERTO_HTTPS' '443')
    $sitios = (Nombres-Servidor | ForEach-Object { "https://$($_):$https" }) -join ', '
    $barra = { param($r) $r -replace '\\', '/' }
    $texto = Get-Content (Join-Path $script:Raiz 'scripts\Caddyfile.plantilla') -Raw -Encoding UTF8
    $valores = [ordered]@{
        '{{SITIOS}}' = $sitios
        '{{PUERTO_API}}' = (Leer-Env 'PUERTO_API' '9006')
        '{{PUERTO_WEB}}' = (Leer-Env 'PUERTO_WEB' '5206')
        '{{SUFIJO_PUERTO}}' = (Sufijo-Https)
        '{{DATOS}}' = (& $barra (Join-Path $script:DirHttps 'autoridad'))
        '{{DIST}}' = (& $barra (Join-Path $script:Frontend 'dist'))
    }
    foreach ($clave in $valores.Keys) { $texto = $texto.Replace($clave, [string]$valores[$clave]) }
    $archivo = Join-Path $script:DirRun 'Caddyfile'
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($archivo, $texto, $utf8)
    & $script:Caddy validate --config $archivo --adapter caddyfile 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "La configuración HTTPS generada no es válida ($archivo)." }
    return $archivo
}

function Agregar-OrigenesHttps {
    $nombres = Nombres-Servidor
    $origenes = $nombres | ForEach-Object { "https://$_$(Sufijo-Https)" }
    foreach ($par in @(@('ALLOWED_HOSTS', $nombres), @('CORS_ALLOWED_ORIGINS', $origenes), @('CSRF_TRUSTED_ORIGINS', $origenes))) {
        $previos = @((Leer-Env $par[0] '') -split ',' | Where-Object { $_ })
        Escribir-Env $par[0] ((@($par[1]) + $previos | Select-Object -Unique) -join ',')
    }
}

function Configurar-Https([bool]$Quitar = $false) {
    if ($Quitar) {
        Escribir-Env 'HTTPS' 'False'
        Escribir-Aviso 'HTTPS desactivado: el sistema vuelve a http. Si usaba start.bat red, ejecútelo de nuevo.'
        Detener 'frontend'; Detener 'backend'
        Iniciar
        return
    }
    Obtener-Caddy
    $https = [int](Leer-Env 'PUERTO_HTTPS' '443')
    if (Puerto-Ajeno $https) {
        $nuevo = Buscar-PuertoLibre 8443 @([int](Leer-Env 'PUERTO_API' '9006'), [int](Leer-Env 'PUERTO_WEB' '5206'))
        Escribir-Aviso "El puerto $https está ocupado por $(Describir-Puerto $https): HTTPS usará el $nuevo."
        $https = $nuevo
    }
    Escribir-Env 'PUERTO_HTTPS' $https
    Escribir-Env 'HTTPS' 'True'
    Escribir-Env 'MODO' 'produccion'
    Escribir-Env 'DEBUG' 'False'
    Agregar-OrigenesHttps
    Escribir-Ok 'Modo producción con HTTPS configurado en backend\.env.'

    Detener 'frontend'; Detener 'backend'
    Escribir-Titulo 'Compilando el sistema para producción'
    Ejecutar-Npm @('run', 'build')
    Ejecutar-Manage @('collectstatic', '--noinput', '--verbosity', '0')
    Iniciar

    # La autoridad local se crea al primer arranque: se copia para instalarla en las demás computadoras.
    $raiz = Join-Path $script:DirHttps 'autoridad\pki\authorities\local\root.crt'
    for ($i = 0; $i -lt 30 -and -not (Test-Path $raiz); $i++) { Start-Sleep -Milliseconds 500 }
    if (-not (Test-Path $raiz)) { Escribir-Error 'No se generó el certificado: revise start.bat logs (frontend.err.log).'; return }
    $copia = Join-Path $script:DirHttps 'koape-certificado.crt'
    Copy-Item $raiz $copia -Force
    $bat = "@echo off`r`nREM Hace que esta computadora confie en el HTTPS del sistema Koape (solo para el usuario actual).`r`n" +
        "certutil -user -addstore Root `"%~dp0koape-certificado.crt`"`r`npause`r`n"
    [System.IO.File]::WriteAllText((Join-Path $script:DirHttps 'instalar-certificado.bat'), $bat, [System.Text.Encoding]::ASCII)
    Escribir-Aviso 'Windows va a preguntar si confía en el certificado «Caddy Local Authority»: responda Sí.'
    Import-Certificate -FilePath $copia -CertStoreLocation Cert:\CurrentUser\Root | Out-Null
    Escribir-Ok 'Esta computadora ya confía en el certificado.'
    Write-Host ''
    Write-Host '    En las DEMÁS computadoras: copie la carpeta https\ y ejecute instalar-certificado.bat,'
    Write-Host "    o abra http://$(Ip-Local):$(Leer-Env 'PUERTO_WEB' '5206')/certificado.crt y ábralo (Instalar certificado →"
    Write-Host '    Entidades de certificación raíz de confianza). Celulares: ver el manual, sección «HTTPS».'
    if (Get-NetFirewallRule -DisplayName 'Koape Aguateras (Web)' -ErrorAction SilentlyContinue) {
        Escribir-Aviso 'El acceso por red ya estaba abierto: ahora se abre el puerto HTTPS.'
        Habilitar-Red
    }
}

# --- Respaldos -----------------------------------------------------------------------------------------
function Exigir-Archivo {
    if (-not $Archivo) { Escribir-Error "Indique el archivo: start.bat $Comando ruta\del\respaldo.zip"; exit 1 }
    if (-not (Test-Path $Archivo)) { Escribir-Error "No existe: $Archivo"; exit 1 }
    return (Resolve-Path $Archivo).Path
}

function Restaurar {
    $zip = Exigir-Archivo
    Escribir-Titulo 'Verificando el respaldo'
    Ejecutar-Manage @('verificar_respaldo', $zip)
    Escribir-Titulo 'Restaurando (el sistema se detiene mientras tanto)'
    Detener 'frontend'; Detener 'backend'
    try {
        Ejecutar-Manage @('restaurar_respaldo', $zip)
    } finally {
        Iniciar
    }
}

function Programar-Respaldo([bool]$Quitar = $false) {
    Unregister-ScheduledTask -TaskName $script:TareaRespaldo -Confirm:$false -ErrorAction SilentlyContinue
    if ($Quitar) { Escribir-Ok 'Respaldo diario desactivado.'; return }
    $hora = Leer-Env 'HORA_RESPALDO' '03:10'
    $log = Join-Path $script:DirLogs 'respaldo.log'
    $accion = New-ScheduledTaskAction -Execute 'cmd.exe' -WorkingDirectory $script:Raiz `
        -Argument "/c `"`"$(Join-Path $script:Raiz 'start.bat')`" respaldo >> `"$log`" 2>&1`""
    $cuando = New-ScheduledTaskTrigger -Daily -At $hora
    # Si a esa hora la computadora estaba apagada, se hace apenas se encienda.
    $ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3) -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries
    Register-ScheduledTask -TaskName $script:TareaRespaldo -Action $accion -Trigger $cuando -Settings $ajustes `
        -Description 'Respaldo completo de Koape Aguateras (start.bat respaldo).' | Out-Null
    Escribir-Ok "Respaldo diario programado a las $hora (tarea «$($script:TareaRespaldo)»). Registro: $log"
    $copia = Leer-Env 'DIR_RESPALDOS_COPIA' ''
    if (-not $copia) { Escribir-Aviso 'Recomendado: DIR_RESPALDOS_COPIA en backend\.env (disco externo o carpeta de red) para tener una copia fuera de esta computadora.' }
    Escribir-Aviso 'La tarea corre con la sesión de este usuario iniciada (la computadora puede estar bloqueada).'
}

switch ($Comando) {
    'start' { Iniciar }
    'stop' { Detener 'frontend'; Detener 'backend' }
    'status' { Estado }
    'restart' { Detener 'frontend'; Detener 'backend'; Start-Sleep -Seconds 1; Iniciar }
    'logs' { Ver-Logs }
    'update' { Actualizar }
    'red' { Habilitar-Red }
    'red-quitar' { Habilitar-Red $true }
    'https' { Configurar-Https }
    'https-quitar' { Configurar-Https $true }
    'respaldo' { Ejecutar-Manage @('respaldar') }
    'respaldo-programar' { Programar-Respaldo }
    'respaldo-quitar' { Programar-Respaldo $true }
    'verificar' { Ejecutar-Manage @('verificar_respaldo', (Exigir-Archivo)) }
    'restaurar' { Restaurar }
    'seguridad' { Ejecutar-Manage @('verificar_seguridad') }
    'datos-prueba' { Ejecutar-Manage @('cargar_datos_prueba', $(if ($Archivo) { $Archivo } else { 'DEMO' })) }
}
