#!/usr/bin/env bash
# Instala Koape Aguateras en un servidor Fedora (Cloud), junto a otros proyectos.
#   bash /home/webuser/AGUATERA-KOAPE/scripts/servidor/instalar_fedora.sh [dominio] [correo-para-letsencrypt]
# Se ejecuta como root. El código, el entorno y los datos quedan a nombre de webuser. Idempotente.
# Regla de oro: nunca asume que el servidor está vacío (servidor web, PostgreSQL y puertos se reutilizan
# o se buscan libres; nunca se pisa la configuración de otros proyectos).
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/comun_servidor.sh"
exigir_root

DOMINIO="${1:-$(leer_env DOMINIO "$DOMINIO_POR_DEFECTO")}"
CORREO="${2:-$(leer_env CORREO_CERTIFICADO '')}"
WEB="$(servidor_web)"
PUERTO="$(leer_env PUERTO_API_SERVIDOR '')"; [[ -n "$PUERTO" ]] || PUERTO="$(puerto_libre 8115)"
MOTOR_ACTUAL="$(leer_env DB_MOTOR sqlite)"

printf '\n  \033[35mKOAPE · Aguateras\033[0m · instalación en servidor\n'
titulo "Esto es lo que se va a hacer"
echo "    Proyecto:          $RAIZ (usuario $USUARIO_APP)"
echo "    Dominio:           $DOMINIO   (su DNS debe apuntar a este servidor para el certificado HTTPS)"
echo "    Servidor web:      $WEB $( [[ $WEB == ninguno ]] && echo '→ se instala Caddy (HTTPS automático)' || echo '→ se agrega UN sitio nuevo; los demás no se tocan')"
echo "    Backend:           127.0.0.1:$PUERTO (servicio $NOMBRE)"
echo "    Frontend:          $WEB_PUBLICA"
echo "    Base de datos:     PostgreSQL (base $NOMBRE_BD; si PostgreSQL ya existe se reutiliza sin tocar otras bases)"
echo "    SELinux:           $(command -v getenforce >/dev/null && getenforce || echo 'no instalado')"
echo "    Tareas:            respaldo diario 03:20 (se conservan los últimos 4)"
read -r -p "    ¿Continuar? (s/N) " r; [[ "${r,,}" == s* ]] || { aviso "Cancelado: no se cambió nada."; exit 0; }

titulo "Paquetes del sistema"
id "$USUARIO_APP" >/dev/null 2>&1 || { useradd -m "$USUARIO_APP"; ok "Usuario $USUARIO_APP creado (sin contraseña: no se ingresa con él)."; }
PAQ=(python3 python3-pip git rsync nodejs npm sqlite policycoreutils-python-utils)
[[ $WEB == ninguno ]] && PAQ+=(caddy)
dnf install -y "${PAQ[@]}" >/dev/null
[[ $WEB == ninguno ]] && { WEB=caddy; systemctl enable --now caddy; }
ok "Python $(python3 --version | cut -d' ' -f2) · Node $(node --version) · servidor web: $WEB"
chown -R "$USUARIO_APP:$USUARIO_APP" "$RAIZ"

titulo "Configuración (backend/.env, solo legible por $USUARIO_APP)"
[[ -f "$ARCHIVO_ENV" ]] || cp "$BACKEND/.env.example" "$ARCHIVO_ENV"
[[ -n "$(leer_env SECRET_KEY)" ]] || escribir_env SECRET_KEY "$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
[[ -n "$(leer_env CLAVE_CIFRADO)" ]] || escribir_env CLAVE_CIFRADO "$(leer_env SECRET_KEY)"
if [[ "$(leer_env ADMIN_PLATAFORMA_CONTRASENA)" == "Koape.Admin.2026" || -z "$(leer_env ADMIN_PLATAFORMA_CONTRASENA)" ]]; then
  escribir_env ADMIN_PLATAFORMA_CONTRASENA "$(python3 -c 'import secrets; print("Kp-" + secrets.token_urlsafe(12))')"
fi
escribir_env DEBUG False
escribir_env MODO produccion
escribir_env HTTPS True
escribir_env PUERTO_API_SERVIDOR "$PUERTO"
escribir_env RESPALDOS_A_CONSERVAR 4
escribir_env NUM_PROXIES 1          # detrás del servidor web: límite de ingreso e IP de auditoría con la IP real
[[ -n "$CORREO" ]] && escribir_env CORREO_CERTIFICADO "$CORREO"
configurar_dominio_env "$DOMINIO"
chown "$USUARIO_APP:$USUARIO_APP" "$ARCHIVO_ENV"; chmod 600 "$ARCHIVO_ENV"
ok "Listo."

titulo "Base de datos (PostgreSQL)"
if [[ "$MOTOR_ACTUAL" == sqlite && -f "$BACKEND/datos/aguateras.sqlite3" ]]; then
  aviso "Ya hay datos en SQLite: no se cambia de motor automáticamente."
  aviso "Pase los datos con el panel «Migración de base de datos» o: manage.py migrate_to_postgres"
else
  preparar_postgres
  chown "$USUARIO_APP:$USUARIO_APP" "$ARCHIVO_ENV"; chmod 600 "$ARCHIVO_ENV"
fi

titulo "Backend"
preparar_backend
manage_app asegurar_admin_plataforma
ok "Base al día y administrador de la plataforma listo."

titulo "Frontend"
publicar_frontend
ok "Publicado en $WEB_PUBLICA."

titulo "Servicios"
if selinux_activo; then setsebool -P httpd_can_network_connect 1; fi
escribir_servicios "$PUERTO"
sleep 2
curl -fsS "http://127.0.0.1:$PUERTO/api/v1/salud/" >/dev/null && ok "Backend respondiendo." || aviso "El backend no responde: journalctl -u $NOMBRE -n 50"

titulo "Sitio web y HTTPS"
if systemctl is-active --quiet firewalld; then firewall-cmd -q --permanent --add-service=http --add-service=https && firewall-cmd -q --reload; fi
escribir_sitio "$WEB" "$DOMINIO" "$PUERTO"
certificado "$WEB" "$DOMINIO" "$CORREO"

titulo "Instalación terminada"
echo "    Sistema:             https://$DOMINIO/"
echo "    Panel plataforma:    https://$DOMINIO/admin/   usuario $(leer_env ADMIN_PLATAFORMA_USUARIO admin) · contraseña $(leer_env ADMIN_PLATAFORMA_CONTRASENA)"
echo "    Instituciones demo:  bash -c 'cd $BACKEND && sudo -u $USUARIO_APP venv/bin/python manage.py crear_institucion_demo'  (opcional)"
echo "    Actualizar:          bash $RAIZ/scripts/servidor/actualizar.sh"
echo "    Cambiar de dominio:  bash $RAIZ/scripts/servidor/cambiar_dominio.sh nuevo.dominio.com"
echo "    Correo (SMTP):       bash $RAIZ/scripts/servidor/configurar_correo.sh   (para el PIN del portal y recuperar contraseñas)"
aviso "Guarde la contraseña del panel y cámbiela al ingresar. Está en $ARCHIVO_ENV (solo $USUARIO_APP y root la leen)."
