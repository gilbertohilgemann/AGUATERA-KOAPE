#!/usr/bin/env bash
# Configura el servidor de correo (SMTP) para el PIN del portal y para recuperar contraseñas. Como root:
#   bash configurar_correo.sh
# Pregunta los datos (o los toma de variables: SMTP_SERVIDOR, SMTP_PUERTO, SMTP_USUARIO, SMTP_CONTRASENA,
# SMTP_SEGURIDAD=tls|ssl, SMTP_REMITENTE, SMTP_PRUEBA=correo@destino), los guarda en backend/.env (solo legible por
# el usuario de la app), reinicia el backend y envía un correo de prueba.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/comun_servidor.sh"
exigir_root

preguntar() {  # $1 variable de entorno, $2 texto, $3 valor por defecto, $4 "secreto" para no mostrarlo
  local valor="${!1:-}"
  if [[ -z "$valor" ]]; then
    if [[ "${4:-}" == secreto ]]; then read -r -s -p "    $2: " valor; echo; else read -r -p "    $2${3:+ [$3]}: " valor; fi
  fi
  echo "${valor:-$3}"
}

titulo "Correo del sistema (SMTP)"
echo "    Lo usan el PIN del portal de abonados y «¿Olvidó su contraseña?». Datos de su proveedor de correo."
SERVIDOR="$(preguntar SMTP_SERVIDOR 'Servidor SMTP (ej. smtp.gmail.com)' "$(leer_env EMAIL_HOST '')")"
[[ -n "$SERVIDOR" ]] || { error "Falta el servidor SMTP."; exit 1; }
SEGURIDAD="$(preguntar SMTP_SEGURIDAD 'Seguridad: tls (puerto 587) o ssl (puerto 465)' tls)"
PUERTO_DEF=587; [[ "${SEGURIDAD,,}" == ssl ]] && PUERTO_DEF=465
PUERTO="$(preguntar SMTP_PUERTO 'Puerto' "$(leer_env EMAIL_PORT "$PUERTO_DEF")")"
USUARIO="$(preguntar SMTP_USUARIO 'Usuario (normalmente la dirección de correo)' "$(leer_env EMAIL_HOST_USER '')")"
CONTRASENA="$(preguntar SMTP_CONTRASENA 'Contraseña (o contraseña de aplicación)' '' secreto)"
[[ -n "$CONTRASENA" ]] || CONTRASENA="$(leer_env EMAIL_HOST_PASSWORD '')"
REMITENTE="$(preguntar SMTP_REMITENTE 'Remitente que verán los usuarios' "Koape Aguateras <$USUARIO>")"
[[ "$CONTRASENA" != *\\* ]] || { error "La contraseña no puede tener barras invertidas (\\)."; exit 1; }

escribir_env EMAIL_HOST "$SERVIDOR"
escribir_env EMAIL_PORT "$PUERTO"
escribir_env EMAIL_HOST_USER "$USUARIO"
escribir_env EMAIL_HOST_PASSWORD "$CONTRASENA"
if [[ "${SEGURIDAD,,}" == ssl ]]; then escribir_env EMAIL_USE_SSL 1; escribir_env EMAIL_USE_TLS 0
else escribir_env EMAIL_USE_SSL 0; escribir_env EMAIL_USE_TLS 1; fi
escribir_env CORREO_REMITENTE "$REMITENTE"
chown "$USUARIO_APP:$USUARIO_APP" "$ARCHIVO_ENV"; chmod 600 "$ARCHIVO_ENV"
systemctl restart "$NOMBRE.service"
ok "Guardado en $ARCHIVO_ENV (solo $USUARIO_APP y root lo leen) y backend reiniciado."

DESTINO="$(preguntar SMTP_PRUEBA 'Enviar un correo de prueba a (vacío = no enviar)' '')"
if [[ -n "$DESTINO" ]]; then
  if manage_app sendtestemail "$DESTINO"; then ok "Correo de prueba enviado a $DESTINO: revise la bandeja (y «correo no deseado»)."
  else aviso "No se pudo enviar. Revise los datos y vuelva a ejecutar este script."; fi
fi
