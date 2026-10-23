#!/usr/bin/env bash
# Restaura un respaldo en el servidor. Como root:
#   bash restaurar.sh /ruta/koape-aguateras-respaldo-....zip
# Verifica el archivo, guarda un respaldo de lo actual (para deshacer), detiene el backend, restaura y lo vuelve a arrancar.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/comun_servidor.sh"
exigir_root
ZIP="$(readlink -f "${1:?Indique el archivo .zip del respaldo}")"
[[ -f "$ZIP" ]] || { error "No existe $ZIP"; exit 1; }
chmod a+r "$ZIP"   # lo tiene que poder leer $USUARIO_APP
titulo "Verificando el respaldo"
manage_app verificar_respaldo "$ZIP"
read -r -p "    Se reemplazan los datos actuales por los del respaldo. Escriba SI para continuar: " r
[[ "$r" == "SI" ]] || { aviso "Cancelado: no se cambió nada."; exit 0; }
titulo "Restaurando (el sistema se detiene mientras tanto)"
systemctl stop "$NOMBRE.service"
if manage_app restaurar_respaldo "$ZIP" --si; then ok "Restaurado."; else error "La restauración falló: se vuelve a arrancar con lo que había."; fi
manage_app migrate --noinput
systemctl start "$NOMBRE.service"
ok "Sistema en marcha."
