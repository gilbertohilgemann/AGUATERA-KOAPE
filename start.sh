#!/usr/bin/env bash
# Arranque de Koape Aguateras en Linux: start | stop | status | restart | update | logs | https | https-quitar
#   | respaldo | respaldo-programar | respaldo-quitar | verificar <zip> | restaurar <zip> | seguridad | datos-prueba
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$PROJECT_ROOT/scripts/comun.sh"
mkdir -p "$DIR_RUN" "$DIR_LOGS"

detener() {
  local p; p="$(leer_pid "$1")"
  if proceso_vivo "$p"; then
    # Se mata el grupo de procesos completo (runserver y npm tienen hijos).
    kill -TERM -- "-$p" 2>/dev/null || kill -TERM "$p" 2>/dev/null || true
    sleep 1; kill -KILL -- "-$p" 2>/dev/null || true
    ok "$1 detenido (PID $p)."
  fi
  rm -f "$DIR_RUN/$1.pid"
}

lanzar() {  # $1 nombre, $2 carpeta, resto: comando
  local nombre="$1" carpeta="$2"; shift 2
  (cd "$carpeta" && setsid nohup "$@" >"$DIR_LOGS/$nombre.log" 2>&1 & echo $! >"$DIR_RUN/$nombre.pid")
  ok "$nombre iniciado (PID $(leer_pid "$nombre"))."
}

estado() {
  local n p
  if esta_https; then
    for n in backend frontend; do p="$(leer_pid "$n")"; if proceso_vivo "$p"; then ok "$n en marcha (PID $p)"; else aviso "$n detenido"; fi; done
    echo "    Sistema:             https://localhost$(sufijo_https)/"
    [[ -n "$(ip_local)" ]] && echo "    Desde la red local:  https://$(ip_local)$(sufijo_https)/"
    echo "    Panel de plataforma: https://localhost$(sufijo_https)/admin/"
    echo "    Certificado:         http://$(ip_local):$(leer_env PUERTO_WEB 5206)/certificado.crt"
    return
  fi
  for n in backend frontend; do
    p="$(leer_pid "$n")"
    if proceso_vivo "$p"; then ok "$n en marcha (PID $p)"; else aviso "$n detenido"; fi
  done
  echo "    Sistema:             http://localhost:$(leer_env PUERTO_WEB 5206)/"
  [[ -n "$(ip_local)" ]] && echo "    Desde la red local:  http://$(ip_local):$(leer_env PUERTO_WEB 5206)/"
  echo "    Panel de plataforma: http://localhost:$(leer_env PUERTO_API 9006)/admin/"
  echo "    Logs:                $DIR_LOGS"
}

iniciar() {
  [[ -x "$PYTHON_VENV" ]] || { error "Falta instalar: ejecute ./install.sh primero."; exit 1; }
  if [[ -n "$(pids_nuestros)" ]]; then aviso "El sistema ya está en marcha."; estado; return; fi
  asegurar_puertos
  local modo; modo="$(leer_env MODO desarrollo)"
  if esta_https; then
    obtener_caddy; escribir_caddyfile
    lanzar backend "$BACKEND" "$PYTHON_VENV" -m waitress --listen="127.0.0.1:$PUERTO_API" configuracion.wsgi:application
    lanzar frontend "$PROJECT_ROOT" "$CADDY" run --config "$DIR_RUN/Caddyfile" --adapter caddyfile
  elif [[ "$modo" == "produccion" ]]; then
    if [[ "$CAMBIO_API" == 1 || ! -d "$FRONTEND/dist" ]]; then aviso "Rearmando el frontend."; npm_web run build; fi
    lanzar backend "$BACKEND" "$PYTHON_VENV" -m waitress --listen="0.0.0.0:$PUERTO_API" configuracion.wsgi:application
    lanzar frontend "$FRONTEND" npm run preview -- --port "$PUERTO_WEB" --strictPort
  else
    lanzar backend "$BACKEND" "$PYTHON_VENV" manage.py runserver "0.0.0.0:$PUERTO_API"
    lanzar frontend "$FRONTEND" npm run dev -- --port "$PUERTO_WEB" --strictPort
  fi
  sleep 3
  estado
}

actualizar() {
  # Desplegar una versión nueva: sobrescribir los archivos nunca alcanza.
  detener frontend; detener backend
  "$PYTHON_VENV" -m pip install -r "$BACKEND/requirements.txt" --quiet
  generar_migraciones_faltantes
  manage migrate --noinput
  manage collectstatic --noinput --verbosity 0
  npm_web install --no-fund --no-audit
  [[ "$(leer_env MODO desarrollo)" == "produccion" ]] && npm_web run build
  iniciar
}

# --- HTTPS (Caddy, versión fija con firma verificada) ---------------------------------------------------
CADDY_VERSION=2.8.4
CADDY_SHA512=b8bec15d14fb033562af9f207850027bcbaa1f891edc9efe00d38bf39e1bf9944f8b6b8eba041ddd4c171cd70c905174c704d705be2f23bc678fe1eaf37a2485
CADDY="$PROJECT_ROOT/herramientas/caddy/caddy"
DIR_HTTPS="$PROJECT_ROOT/https"

esta_https() { [[ "$(leer_env HTTPS False)" =~ ^(True|true|1)$ ]]; }
sufijo_https() { local p; p="$(leer_env PUERTO_HTTPS 8443)"; [[ "$p" == 443 ]] && echo "" || echo ":$p"; }
nombres_servidor() { { echo localhost; echo 127.0.0.1; hostname | tr 'A-Z' 'a-z'; hostname -I 2>/dev/null | tr ' ' '\n'; } | grep -v '^$' | grep -v ':' | awk '!v[$0]++'; }

obtener_caddy() {
  [[ -x "$CADDY" ]] && return
  titulo "Descargando el servidor HTTPS (Caddy $CADDY_VERSION)"
  local tmp; tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/caddy.tar.gz" "https://github.com/caddyserver/caddy/releases/download/v$CADDY_VERSION/caddy_${CADDY_VERSION}_linux_amd64.tar.gz"
  if [[ "$(sha512sum "$tmp/caddy.tar.gz" | cut -d' ' -f1)" != "$CADDY_SHA512" ]]; then
    rm -rf "$tmp"; error "La descarga de Caddy no coincide con la firma publicada: no se instala."; exit 1
  fi
  mkdir -p "$(dirname "$CADDY")"; tar -xzf "$tmp/caddy.tar.gz" -C "$(dirname "$CADDY")" caddy; rm -rf "$tmp"
  ok "Caddy $CADDY_VERSION instalado (firma verificada)."
}

escribir_caddyfile() {
  local https sitios
  https="$(leer_env PUERTO_HTTPS 8443)"
  sitios="$(nombres_servidor | sed "s#.*#https://&:$https#" | paste -sd, - | sed 's/,/, /g')"
  sed -e "s#{{SITIOS}}#$sitios#g" -e "s#{{PUERTO_API}}#$(leer_env PUERTO_API 9006)#g" -e "s#{{PUERTO_WEB}}#$(leer_env PUERTO_WEB 5206)#g" \
      -e "s#{{SUFIJO_PUERTO}}#$(sufijo_https)#g" -e "s#{{DATOS}}#$DIR_HTTPS/autoridad#g" -e "s#{{DIST}}#$FRONTEND/dist#g" \
      "$PROJECT_ROOT/scripts/Caddyfile.plantilla" > "$DIR_RUN/Caddyfile"
  "$CADDY" validate --config "$DIR_RUN/Caddyfile" --adapter caddyfile >/dev/null 2>&1 || { error "Configuración HTTPS inválida ($DIR_RUN/Caddyfile)."; exit 1; }
}

agregar_origenes_https() {
  local nombres origenes clave previos
  nombres="$(nombres_servidor | paste -sd, -)"
  origenes="$(nombres_servidor | sed "s#.*#https://&$(sufijo_https)#" | paste -sd, -)"
  for clave in ALLOWED_HOSTS CORS_ALLOWED_ORIGINS CSRF_TRUSTED_ORIGINS; do
    previos="$(leer_env "$clave" '')"
    if [[ "$clave" == ALLOWED_HOSTS ]]; then nuevo="$nombres"; else nuevo="$origenes"; fi
    escribir_env "$clave" "$(echo "$nuevo,$previos" | tr ',' '\n' | grep -v '^$' | awk '!v[$0]++' | paste -sd, -)"
  done
}

configurar_https() {
  if [[ "${1:-}" == quitar ]]; then
    escribir_env HTTPS False; aviso "HTTPS desactivado."; detener frontend; detener backend; iniciar; return
  fi
  obtener_caddy
  local https; https="$(leer_env PUERTO_HTTPS 8443)"   # 443 en Linux exige permisos de root
  if puerto_ajeno "$https"; then https="$(buscar_puerto_libre 8444 "$(leer_env PUERTO_API 9006)")"; aviso "HTTPS usará el puerto $https."; fi
  escribir_env PUERTO_HTTPS "$https"; escribir_env HTTPS True; escribir_env MODO produccion; escribir_env DEBUG False
  agregar_origenes_https
  detener frontend; detener backend
  npm_web run build; manage collectstatic --noinput --verbosity 0
  iniciar
  local raiz="$DIR_HTTPS/autoridad/pki/authorities/local/root.crt" i
  for i in $(seq 30); do [[ -f "$raiz" ]] && break; sleep 0.5; done
  [[ -f "$raiz" ]] || { error "No se generó el certificado (ver logs/frontend.log)."; return; }
  cp "$raiz" "$DIR_HTTPS/koape-certificado.crt"
  ok "Certificado para instalar en las demás computadoras: $DIR_HTTPS/koape-certificado.crt"
  echo "    (en Linux: sudo cp ese archivo a /usr/local/share/ca-certificates/ y sudo update-ca-certificates)"
}

# --- Respaldos ------------------------------------------------------------------------------------------
exigir_archivo() {
  [[ -n "${1:-}" ]] || { error "Indique el archivo: $0 ${ACCION} ruta/del/respaldo.zip"; exit 1; }
  [[ -f "$1" ]] || { error "No existe: $1"; exit 1; }
  realpath "$1"
}

restaurar() {
  local zip; zip="$(exigir_archivo "${1:-}")"
  titulo "Verificando el respaldo"; manage verificar_respaldo "$zip"
  titulo "Restaurando (el sistema se detiene mientras tanto)"
  detener frontend; detener backend
  manage restaurar_respaldo "$zip" || { iniciar; exit 1; }
  iniciar
}

programar_respaldo() {
  local linea marca="# koape-respaldo"
  local hora; hora="$(leer_env HORA_RESPALDO 03:10)"
  command -v crontab >/dev/null || { error "No está instalado cron (crontab): instálelo o programe '$PROJECT_ROOT/start.sh respaldo' a mano."; return 1; }
  crontab -l 2>/dev/null | grep -v "$marca" > "$DIR_RUN/crontab" || true
  if [[ "${1:-}" != quitar ]]; then
    linea="${hora#*:} ${hora%%:*} * * * \"$PROJECT_ROOT/start.sh\" respaldo >> \"$DIR_LOGS/respaldo.log\" 2>&1 $marca"
    echo "$linea" >> "$DIR_RUN/crontab"
  fi
  crontab "$DIR_RUN/crontab" || { error "No se pudo guardar el crontab."; return 1; }
  if [[ "${1:-}" == quitar ]]; then ok "Respaldo diario desactivado."; else ok "Respaldo diario programado a las $hora (crontab)."; fi
}

ACCION="${1:-start}"
case "$ACCION" in
  start) iniciar ;;
  stop) detener frontend; detener backend ;;
  status) estado ;;
  restart) detener frontend; detener backend; sleep 1; iniciar ;;
  update) actualizar ;;
  logs) tail -n 40 "$DIR_LOGS"/*.log ;;
  https) configurar_https ;;
  https-quitar) configurar_https quitar ;;
  respaldo) manage respaldar ;;
  respaldo-programar) programar_respaldo ;;
  respaldo-quitar) programar_respaldo quitar ;;
  verificar) manage verificar_respaldo "$(exigir_archivo "${2:-}")" ;;
  restaurar) restaurar "${2:-}" ;;
  seguridad) manage verificar_seguridad ;;
  datos-prueba) manage cargar_datos_prueba "${2:-DEMO}" ;;
  *) echo "Uso: $0 {start|stop|status|restart|update|logs|https|https-quitar|respaldo|respaldo-programar|respaldo-quitar|verificar <zip>|restaurar <zip>|seguridad|datos-prueba}"; exit 1 ;;
esac
