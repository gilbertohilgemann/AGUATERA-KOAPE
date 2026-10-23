#!/usr/bin/env bash
# Reintenta el certificado HTTPS (cuando el DNS ya apunta al servidor). Como root.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/comun_servidor.sh"
exigir_root
certificado "$(servidor_web)" "$(leer_env DOMINIO "$DOMINIO_POR_DEFECTO")" "$(leer_env CORREO_CERTIFICADO '')"
