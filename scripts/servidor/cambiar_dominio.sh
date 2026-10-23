#!/usr/bin/env bash
# Pasa el sistema a otro dominio: bash cambiar_dominio.sh nuevo.dominio.com [correo]. Como root.
# Nada del sistema tiene el dominio escrito: vive en backend/.env y en el sitio del servidor web.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/comun_servidor.sh"
exigir_root
NUEVO="${1:?Indique el dominio nuevo, ej.: bash cambiar_dominio.sh reservas.ejemplo.com}"
CORREO="${2:-$(leer_env CORREO_CERTIFICADO '')}"
ANTERIOR="$(leer_env DOMINIO '')"
WEB="$(servidor_web)"
configurar_dominio_env "$NUEVO"
systemctl restart "$NOMBRE.service"
escribir_sitio "$WEB" "$NUEVO" "$(leer_env PUERTO_API_SERVIDOR 8115)"
certificado "$WEB" "$NUEVO" "$CORREO"
ok "Dominio cambiado: ${ANTERIOR:-?} → $NUEVO. El DNS de $NUEVO debe apuntar a este servidor."
