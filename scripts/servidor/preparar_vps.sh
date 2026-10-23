#!/usr/bin/env bash
# Primer paso en un VPS Fedora nuevo: deja todo listo para bajar Koape Aguateras desde GitHub (repositorio privado)
# e instalarlo. Como root. Se puede volver a ejecutar sin problema (lo que ya existe se reutiliza).
#   bash preparar_vps.sh [usuario-o-organizacion-de-github] [dominio] [correo-para-https]
# 1) usuario webuser y su carpeta · 2) git · 3) clave SSH de SOLO LECTURA del VPS (deploy key) · 4) espera a que la
# cargue en GitHub y prueba el acceso · 5) baja (o actualiza) el código en /home/webuser/AGUATERA-KOAPE · 6) instala.
set -euo pipefail

CUENTA="${1:-gilbertohilgemann}"
DOMINIO="${2:-aguateras.koapesystem.com}"
CORREO="${3:-}"
USUARIO=webuser
REPO="AGUATERA-KOAPE"
DESTINO="/home/$USUARIO/$REPO"
CLAVE="/home/$USUARIO/.ssh/aguateras_github"
ALIAS="github-aguateras"

titulo() { printf '\n\033[35m==> %s\033[0m\n' "$1"; }
ok() { printf '    \033[32m[ok]\033[0m %s\n' "$1"; }
[[ $EUID -eq 0 ]] || { echo "Ejecute como root (sudo -i)."; exit 1; }

titulo "1. Usuario de la aplicación ($USUARIO)"
if id "$USUARIO" >/dev/null 2>&1; then ok "Ya existe."; else useradd -m "$USUARIO"; ok "Creado (sin contraseña: nadie ingresa con él)."; fi

titulo "2. Git"
command -v git >/dev/null || dnf install -y git >/dev/null
ok "$(git --version)"

titulo "3. Clave SSH del VPS (solo lectura del repositorio)"
install -d -m 700 -o "$USUARIO" -g "$USUARIO" "/home/$USUARIO/.ssh"
if [[ ! -f "$CLAVE" ]]; then
  sudo -u "$USUARIO" ssh-keygen -q -t ed25519 -N "" -C "vps-aguateras" -f "$CLAVE"
  ok "Clave creada."
else
  ok "Ya existía: se usa la misma."
fi
CONFIG="/home/$USUARIO/.ssh/config"
if ! grep -q "^Host $ALIAS\$" "$CONFIG" 2>/dev/null; then
  printf 'Host %s\n  HostName github.com\n  User git\n  IdentityFile %s\n  IdentitiesOnly yes\n' "$ALIAS" "$CLAVE" >> "$CONFIG"
fi
chown "$USUARIO:$USUARIO" "$CONFIG"; chmod 600 "$CONFIG"

titulo "4. Cargar la clave en GitHub"
echo "    Copie esta línea completa:"
echo
cat "$CLAVE.pub"
echo
echo "    En GitHub: repositorio $CUENTA/$REPO → Settings → Deploy keys → Add deploy key"
echo "    Título: VPS · pegue la línea · NO marque «Allow write access» · Add key"
acceso() {  # «ssh -T» a GitHub siempre termina con código 1: se mira el mensaje
  local salida; salida="$(sudo -u "$USUARIO" ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes -T "$ALIAS" 2>&1 || true)"
  [[ "$salida" == *"successfully authenticated"* ]]
}
until acceso; do
  read -r -p "    Cuando la haya agregado, pulse Enter para probar (o Ctrl+C para salir)... " _
done
ok "GitHub reconoce la clave del VPS."

titulo "5. Código en $DESTINO"
if [[ -d "$DESTINO/.git" ]]; then
  sudo -u "$USUARIO" git -C "$DESTINO" pull --ff-only
  ok "Actualizado."
else
  sudo -u "$USUARIO" git clone "$ALIAS:$CUENTA/$REPO.git" "$DESTINO"
  ok "Descargado."
fi

titulo "6. Instalación"
bash "$DESTINO/scripts/servidor/instalar_fedora.sh" "$DOMINIO" "$CORREO"
