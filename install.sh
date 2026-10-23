#!/usr/bin/env bash
# Instalador de Koape Aguateras para Linux. Idempotente: se puede volver a correr al actualizar.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$PROJECT_ROOT/scripts/comun.sh"

printf '\n  \033[35mKOAPE SISTEMAS EAS · Aguateras\033[0m\n  Instalador para Linux\n'

# --- 1. Dependencias del sistema (pide permiso antes de instalar nada) ---------------------
titulo "Revisando dependencias del sistema"
FALTAN=()
if ! command -v python3 >/dev/null || ! python3 -c 'import sys; assert sys.version_info >= (3, 10)' 2>/dev/null; then FALTAN+=(python3); fi
python3 -c 'import venv, ensurepip' 2>/dev/null || FALTAN+=(python3-venv)
command -v npm >/dev/null || FALTAN+=(nodejs npm)
if ((${#FALTAN[@]})); then
  aviso "Faltan: ${FALTAN[*]}"
  if command -v apt-get >/dev/null && preguntar_si_no "¿Instalarlos con apt-get (requiere sudo)?" n; then
    sudo apt-get update && sudo apt-get install -y "${FALTAN[@]}"
  else
    error "Instale manualmente: ${FALTAN[*]} (Python 3.10+, Node.js 20+) y vuelva a ejecutar."; exit 1
  fi
fi
ok "Python: $(python3 --version)"; ok "Node.js: $(node --version)"

if [[ -n "$(pids_nuestros)" ]]; then aviso "El sistema está en marcha: se detiene para actualizar."; "$PROJECT_ROOT/start.sh" stop; fi

# --- 2. Backend ----------------------------------------------------------------------------
titulo "Preparando el backend (Django)"
[[ -x "$PYTHON_VENV" ]] || { python3 -m venv "$BACKEND/venv"; ok "Entorno virtual creado."; }
"$PYTHON_VENV" -m pip install --upgrade pip --quiet
"$PYTHON_VENV" -m pip install -r "$BACKEND/requirements.txt" --quiet
ok "Dependencias de Python instaladas."
[[ -f "$ARCHIVO_ENV" ]] || { cp "$BACKEND/.env.example" "$ARCHIVO_ENV"; ok "Archivo backend/.env creado."; }
if [[ -z "$(leer_env SECRET_KEY)" ]]; then
  escribir_env SECRET_KEY "$("$PYTHON_VENV" -c 'import secrets; print(secrets.token_urlsafe(50))')"; ok "SECRET_KEY generada."
fi
# Igual a SECRET_KEY: es la clave que el sistema ya usa si falta, así nada guardado deja de leerse.
[[ -n "$(leer_env CLAVE_CIFRADO)" ]] || { escribir_env CLAVE_CIFRADO "$(leer_env SECRET_KEY)"; ok "CLAVE_CIFRADO configurada."; }

# --- 3. Puertos -----------------------------------------------------------------------------
titulo "Buscando puertos libres"
asegurar_puertos
ok "API: $PUERTO_API · Web: $PUERTO_WEB"

# --- 4. Base de datos ---------------------------------------------------------------------
titulo "Preparando la base de datos (SQLite por defecto)"
generar_migraciones_faltantes
manage migrate --noinput
manage collectstatic --noinput --verbosity 0
manage asegurar_admin_plataforma
ok "Base de datos al día (SQLite)."
aviso "PostgreSQL es opcional: se migra después, sin perder datos, desde el panel de la plataforma."
if preguntar_si_no "¿Crear las instituciones de DEMOSTRACIÓN (DEMO y DEMO2)?" s; then manage crear_institucion_demo; fi

# --- 5. Frontend -------------------------------------------------------------------------
titulo "Preparando el frontend (React)"
npm_web install --no-fund --no-audit
[[ "$(leer_env MODO desarrollo)" == "produccion" ]] && npm_web run build
ok "Frontend listo."

# --- 6. Arranque automático (solo si se contesta que sí) --------------------------------
if command -v systemctl >/dev/null && preguntar_si_no "¿Activar el arranque automático al reiniciar el servidor (systemd)?" n; then
  SERVICIO=/etc/systemd/system/koape-aguateras.service
  sudo tee "$SERVICIO" >/dev/null <<UNIDAD
[Unit]
Description=Koape Aguateras
After=network.target

[Service]
Type=forking
User=$(id -un)
WorkingDirectory=$PROJECT_ROOT
ExecStart=$PROJECT_ROOT/start.sh start
ExecStop=$PROJECT_ROOT/start.sh stop
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIDAD
  sudo systemctl daemon-reload && sudo systemctl enable koape-aguateras.service
  ok "Arranque automático activado ($SERVICIO)."
fi

# --- 7. Resumen ------------------------------------------------------------------------------
titulo "Instalación terminada"
echo "    Arrancar:            ./start.sh start   (stop | status | restart | update)"
echo "    Sistema:             http://localhost:$PUERTO_WEB/"
[[ -n "$(ip_local)" ]] && echo "    Desde la red local:  http://$(ip_local):$PUERTO_WEB/"
echo "    Panel de plataforma: http://localhost:$PUERTO_API/admin/"
echo "    Usuario plataforma:  $(leer_env ADMIN_PLATAFORMA_USUARIO admin)  /  $(leer_env ADMIN_PLATAFORMA_CONTRASENA)"
echo "    Instituciones demo:  código DEMO o DEMO2 · usuario admin · contraseña Demo.Koape.2026"
aviso "Cambie la contraseña del administrador de la plataforma apenas ingrese al panel."
