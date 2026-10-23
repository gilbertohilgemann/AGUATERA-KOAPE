#!/usr/bin/env bash
# Funciones compartidas por install.sh y start.sh. Rutas calculadas, nunca escritas a mano.
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$PROJECT_ROOT/backend"
FRONTEND="$PROJECT_ROOT/frontend"
DIR_RUN="$PROJECT_ROOT/.run"
DIR_LOGS="$PROJECT_ROOT/logs"
ARCHIVO_ENV="$BACKEND/.env"
ARCHIVO_ENV_WEB="$FRONTEND/.env.local"
PYTHON_VENV="$BACKEND/venv/bin/python"

titulo() { printf '\n\033[35m==> %s\033[0m\n' "$1"; }
ok() { printf '    \033[32m[ok]\033[0m %s\n' "$1"; }
aviso() { printf '    \033[33m[!]\033[0m %s\n' "$1"; }
error() { printf '    \033[31m[x]\033[0m %s\n' "$1"; }

preguntar_si_no() {  # $1 pregunta, $2 por defecto (s|n)
  local por_defecto="${2:-n}" sufijo="(s/N)" r
  [[ "$por_defecto" == "s" ]] && sufijo="(S/n)"
  read -r -p "$1 $sufijo " r || true
  r="${r:-$por_defecto}"
  [[ "${r,,}" == s* ]]
}

leer_env() {  # $1 clave, $2 por defecto
  local valor=""
  [[ -f "$ARCHIVO_ENV" ]] && valor="$(grep -E "^\s*$1\s*=" "$ARCHIVO_ENV" | tail -n1 | cut -d= -f2- | xargs)"
  echo "${valor:-${2:-}}"
}

escribir_env() {  # $1 clave, $2 valor
  touch "$ARCHIVO_ENV"
  if grep -qE "^\s*$1\s*=" "$ARCHIVO_ENV"; then
    local tmp; tmp="$(mktemp)"
    awk -v k="$1" -v v="$2" 'BEGIN{FS=OFS="="} $0 ~ "^[[:space:]]*"k"[[:space:]]*=" {print k"="v; next} {print}' "$ARCHIVO_ENV" > "$tmp"
    cat "$tmp" > "$ARCHIVO_ENV" && rm -f "$tmp"
  else
    echo "$1=$2" >> "$ARCHIVO_ENV"
  fi
}

leer_pid() { [[ -f "$DIR_RUN/$1.pid" ]] && cat "$DIR_RUN/$1.pid" || true; }
proceso_vivo() { [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null; }

pids_nuestros() {
  local n p
  for n in backend frontend; do p="$(leer_pid "$n")"; if proceso_vivo "$p"; then echo "$p"; fi; done
  return 0
}

dueno_puerto() {  # imprime el PID que escucha en el puerto ("?" si no se puede saber); nada si está libre
  local p="$1" linea pid
  if command -v ss >/dev/null 2>&1; then
    linea="$(ss -ltnpH "sport = :$p" 2>/dev/null | head -n1)"
    [[ -z "$linea" ]] && return 0
    pid="$(grep -oE 'pid=[0-9]+' <<<"$linea" | head -n1 | cut -d= -f2)"
    echo "${pid:-?}"
  elif command -v lsof >/dev/null 2>&1; then
    pid="$(lsof -nP -iTCP:"$p" -sTCP:LISTEN -t 2>/dev/null | head -n1)"
    [[ -n "$pid" ]] && echo "$pid"
  else
    (exec 3<>"/dev/tcp/127.0.0.1/$p") 2>/dev/null && echo "?"
  fi
  return 0
}

es_descendiente() {  # $1 pid, resto: pids raíz
  local actual="$1"; shift
  local i
  for i in 1 2 3 4 5 6 7 8; do
    [[ -z "$actual" || "$actual" == "0" ]] && return 1
    for raiz in "$@"; do [[ "$actual" == "$raiz" ]] && return 0; done
    actual="$(ps -o ppid= -p "$actual" 2>/dev/null | xargs)"
  done
  return 1
}

puerto_ajeno() {
  local dueno; dueno="$(dueno_puerto "$1")"
  [[ -z "$dueno" ]] && return 1
  local nuestros; nuestros=($(pids_nuestros))
  if [[ "$dueno" != "?" && ${#nuestros[@]} -gt 0 ]] && es_descendiente "$dueno" "${nuestros[@]}"; then return 1; fi
  return 0
}

describir_puerto() {
  local dueno; dueno="$(dueno_puerto "$1")"
  if [[ "$dueno" =~ ^[0-9]+$ ]]; then echo "PID $dueno ($(ps -o comm= -p "$dueno" 2>/dev/null))"; else echo "un proceso no identificado"; fi
}

buscar_puerto_libre() {  # $1 desde, $2 puerto a evitar
  local p
  for ((p = $1; p < $1 + 200; p++)); do
    [[ "$p" == "${2:-}" ]] && continue
    [[ -z "$(dueno_puerto "$p")" ]] && { echo "$p"; return 0; }
  done
  return 1
}

asegurar_puertos() {  # deja PUERTO_API/PUERTO_WEB; CAMBIO_API=1 si cambió el de la API
  PUERTO_API="$(leer_env PUERTO_API 9006)"; PUERTO_WEB="$(leer_env PUERTO_WEB 5206)"; CAMBIO_API=0
  if puerto_ajeno "$PUERTO_API"; then
    local nuevo; nuevo="$(buscar_puerto_libre $((PUERTO_API + 1)) "$PUERTO_WEB")"
    aviso "El puerto $PUERTO_API está ocupado por $(describir_puerto "$PUERTO_API"). No interfiero: la API usará el $nuevo."
    PUERTO_API="$nuevo"; CAMBIO_API=1
  fi
  if puerto_ajeno "$PUERTO_WEB"; then
    local nuevo; nuevo="$(buscar_puerto_libre $((PUERTO_WEB + 1)) "$PUERTO_API")"
    aviso "El puerto $PUERTO_WEB está ocupado por $(describir_puerto "$PUERTO_WEB"). No interfiero: la web usará el $nuevo."
    PUERTO_WEB="$nuevo"
  fi
  escribir_env PUERTO_API "$PUERTO_API"
  escribir_env PUERTO_WEB "$PUERTO_WEB"
  echo "VITE_API_PUERTO=$PUERTO_API" > "$ARCHIVO_ENV_WEB"
}

manage() { (cd "$BACKEND" && "$PYTHON_VENV" manage.py "$@"); }
npm_web() { (cd "$FRONTEND" && npm "$@"); }
ip_local() { hostname -I 2>/dev/null | awk '{print $1}'; }

generar_migraciones_faltantes() {
  # Genera las migraciones que falten (app nueva o modelo cambiado); sin cambios no hace nada.
  manage makemigrations --noinput plataforma identidad auditoria territorio padron facturacion recorridos lecturas tarifas migracion_bd respaldo manual
  return 0
}
