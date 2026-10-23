#!/usr/bin/env bash
# Baja la última versión de GitHub y la aplica (dependencias, migraciones, frontend). Como root.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/comun_servidor.sh"
exigir_root
titulo "Bajando la última versión"
(cd "$RAIZ" && como_app git pull --ff-only)
titulo "Aplicando"
preparar_backend
publicar_frontend
escribir_servicios "$(leer_env PUERTO_API_SERVIDOR 8115)"
ok "Actualizado: $(cd "$RAIZ" && como_app git log -1 --format='%h %s')"
