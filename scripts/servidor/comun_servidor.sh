#!/usr/bin/env bash
# Funciones del despliegue en servidor (Fedora). Se ejecuta como root; el proyecto pertenece a webuser.
# Convive con otros proyectos (p. ej. Koape Hotel-Restaurante): este sistema se agrega como UN sitio más del servidor web que ya exista
# (nginx, Caddy o Apache) y nunca reescribe la configuración de los demás.
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$RAIZ/scripts/comun.sh"   # leer_env / escribir_env / titulo / ok / aviso / error

USUARIO_APP="${USUARIO_APP:-webuser}"
NOMBRE="koape-aguateras"                       # nombre de servicios, sitio y carpetas
WEB_PUBLICA="/var/www/$NOMBRE"                   # copia compilada del frontend (fuera de /home: sin líos de permisos ni SELinux)
DOMINIO_POR_DEFECTO="aguateras.koapesystem.com"

como_app() { sudo -u "$USUARIO_APP" -H "$@"; }
manage_app() { (cd "$BACKEND" && como_app "$PYTHON_VENV" manage.py "$@"); }

exigir_root() { [[ $EUID -eq 0 ]] || { error "Ejecute como root."; exit 1; }; }

servidor_web() {  # nginx | caddy | httpd | ninguno (el que está activo o, si no, instalado)
  local s
  for s in nginx caddy httpd; do systemctl is-active --quiet "$s" && { echo "$s"; return; }; done
  for s in nginx caddy httpd; do command -v "$s" >/dev/null 2>&1 && { echo "$s"; return; }; done
  echo ninguno
}

puerto_libre() {  # primer puerto libre desde $1
  local p="$1"
  while ss -ltnH "sport = :$p" 2>/dev/null | grep -q .; do p=$((p + 1)); done
  echo "$p"
}

selinux_activo() { command -v getenforce >/dev/null && [[ "$(getenforce)" != "Disabled" ]]; }

publicar_frontend() {  # compila con el usuario de la app y copia el resultado a /var/www
  # Misma dirección para la página y la API (el servidor web reenvía /api): sirve con cualquier dominio.
  printf 'VITE_API_MISMO_ORIGEN=1\n' > "$ARCHIVO_ENV_WEB"; chown "$USUARIO_APP:$USUARIO_APP" "$ARCHIVO_ENV_WEB"
  # npm ci exige package-lock.json (lo genera la primera instalación en desarrollo); si no está, npm install.
  local instalar=install; [[ -f "$FRONTEND/package-lock.json" ]] && instalar=ci
  (cd "$FRONTEND" && como_app npm "$instalar" --no-fund --no-audit && como_app npm run build)
  mkdir -p "$WEB_PUBLICA"
  rsync -a --delete "$FRONTEND/dist/" "$WEB_PUBLICA/"
  chown -R root:root "$WEB_PUBLICA"; chmod -R a+rX "$WEB_PUBLICA"
  if selinux_activo; then restorecon -R "$WEB_PUBLICA" >/dev/null 2>&1 || true; fi
}

escribir_sitio() {  # $1 servidor web, $2 dominio, $3 puerto del backend
  local web="$1" dominio="$2" puerto="$3"
  case "$web" in
    nginx)
      cat > "/etc/nginx/conf.d/$NOMBRE.conf" <<CONF
# Koape Aguateras ($dominio). Generado por scripts/servidor: no editar a mano.
server {
    listen 80;
    listen [::]:80;
    server_name $dominio;
    client_max_body_size 25m;   # fotos de medidores y comprobantes
    root $WEB_PUBLICA;

    location ~ ^/(api|admin|static|media)(/|\$) {
        proxy_pass http://127.0.0.1:$puerto;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
    }
    location /assets/ { expires 30d; add_header Cache-Control "public, immutable"; try_files \$uri =404; }
    # Aplicación del cobrador (PWA): el service worker y el manifiesto se revisan siempre.
    location ~ ^/(sw\.js|manifest\.webmanifest)\$ { add_header Cache-Control "no-cache"; try_files \$uri =404; }
    location / { try_files \$uri /index.html; }
}
CONF
      nginx -t && systemctl reload nginx ;;
    caddy)
      mkdir -p /etc/caddy/Caddyfile.d
      grep -qE '^\s*import\s+Caddyfile\.d/\*' /etc/caddy/Caddyfile 2>/dev/null || printf '\nimport Caddyfile.d/*.caddy\n' >> /etc/caddy/Caddyfile
      cat > "/etc/caddy/Caddyfile.d/$NOMBRE.caddy" <<CONF
# Koape Aguateras. Generado por scripts/servidor: no editar a mano. HTTPS automático (Let's Encrypt).
$dominio {
	encode zstd gzip
	request_body { max_size 25MB }
	@servidor path /api/* /admin /admin/* /static/* /media/*
	handle @servidor { reverse_proxy 127.0.0.1:$puerto }
	handle {
		root * $WEB_PUBLICA
		try_files {path} /index.html
		file_server
	}
	header { Strict-Transport-Security "max-age=31536000"; X-Content-Type-Options nosniff; -Server }
}
CONF
      caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null && systemctl reload caddy ;;
    httpd)
      cat > "/etc/httpd/conf.d/$NOMBRE.conf" <<CONF
# Koape Aguateras ($dominio). Generado por scripts/servidor: no editar a mano.
<VirtualHost *:80>
    ServerName $dominio
    DocumentRoot $WEB_PUBLICA
    LimitRequestBody 26214400
    ProxyPreserveHost On
    RequestHeader set X-Forwarded-Proto expr=%{REQUEST_SCHEME}
    ProxyPassMatch ^/((api|admin|static|media)(/.*)?)\$ http://127.0.0.1:$puerto/\$1
    <Directory $WEB_PUBLICA>
        Require all granted
        FallbackResource /index.html
    </Directory>
</VirtualHost>
CONF
      apachectl configtest && systemctl reload httpd ;;
  esac
}

certificado() {  # $1 servidor web, $2 dominio, $3 correo — HTTPS con Let's Encrypt (Caddy lo hace solo)
  local web="$1" dominio="$2" correo="$3"
  [[ "$web" == caddy ]] && { ok "Caddy obtiene y renueva el certificado solo."; return 0; }
  local plugin="python3-certbot-nginx"; [[ "$web" == httpd ]] && plugin="python3-certbot-apache"
  rpm -q certbot "$plugin" >/dev/null 2>&1 || dnf install -y certbot "$plugin"
  local mail=(--register-unsafely-without-email); [[ -n "$correo" ]] && mail=(-m "$correo")
  if certbot "--${web/httpd/apache}" -d "$dominio" --non-interactive --agree-tos --redirect --keep-until-expiring "${mail[@]}"; then
    ok "Certificado HTTPS instalado para $dominio."
  else
    aviso "No se pudo obtener el certificado. ¿El DNS de $dominio ya apunta a este servidor?"
    aviso "Cuando apunte, ejecute: bash $RAIZ/scripts/servidor/https.sh"
  fi
}

escribir_servicios() {  # backend (waitress) + tareas programadas, todo como el usuario de la app
  local puerto="$1"
  cat > "/etc/systemd/system/$NOMBRE.service" <<UNIDAD
[Unit]
Description=Koape Aguateras (backend)
After=network.target

[Service]
User=$USUARIO_APP
Group=$USUARIO_APP
WorkingDirectory=$BACKEND
ExecStart=$PYTHON_VENV -m waitress --listen=127.0.0.1:$puerto --threads=8 configuracion.wsgi:application
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIDAD
  local tarea comando cuando
  for tarea in respaldo; do
    comando="respaldar"; cuando="*-*-* 03:20:00"
    cat > "/etc/systemd/system/$NOMBRE-$tarea.service" <<UNIDAD
[Unit]
Description=Koape Aguateras: $tarea

[Service]
Type=oneshot
User=$USUARIO_APP
WorkingDirectory=$BACKEND
ExecStart=$PYTHON_VENV manage.py $comando
UNIDAD
    cat > "/etc/systemd/system/$NOMBRE-$tarea.timer" <<UNIDAD
[Unit]
Description=Koape Aguateras: $tarea programado

[Timer]
OnCalendar=$cuando
Persistent=true

[Install]
WantedBy=timers.target
UNIDAD
  done
  systemctl daemon-reload
  systemctl enable --now "$NOMBRE.service" "$NOMBRE-respaldo.timer" >/dev/null
  systemctl restart "$NOMBRE.service"
}

configurar_dominio_env() {  # $1 dominio
  escribir_env DOMINIO "$1"
  escribir_env ALLOWED_HOSTS "$1,127.0.0.1,localhost"
  escribir_env CORS_ALLOWED_ORIGINS "https://$1"
  escribir_env CSRF_TRUSTED_ORIGINS "https://$1"
}

preparar_backend() {
  [[ -x "$PYTHON_VENV" ]] || como_app python3 -m venv "$BACKEND/venv"
  como_app "$PYTHON_VENV" -m pip install --upgrade pip --quiet
  como_app "$PYTHON_VENV" -m pip install -r "$BACKEND/requirements.txt" --quiet
  manage_app migrate --noinput
  manage_app collectstatic --noinput --verbosity 0
}

# --- PostgreSQL (producción, decisión D1) --------------------------------------------------------------
# Nunca asume un servidor vacío: si PostgreSQL ya está instalado y en marcha (otros proyectos), lo reutiliza
# creando SOLO un usuario y una base propios; nunca reinicializa el clúster ni toca las bases de otros.
NOMBRE_BD="koape_aguateras"
USUARIO_BD="koape_aguateras"

preparar_postgres() {
  if ! command -v psql >/dev/null 2>&1 || ! rpm -q postgresql-server >/dev/null 2>&1; then
    dnf install -y postgresql-server postgresql >/dev/null
    ok "PostgreSQL instalado."
  fi
  if [[ ! -f /var/lib/pgsql/data/PG_VERSION ]]; then
    postgresql-setup --initdb >/dev/null && ok "Clúster de PostgreSQL inicializado."
  fi
  systemctl enable --now postgresql >/dev/null
  local clave; clave="$(leer_env DB_CONTRASENA '')"
  [[ -n "$clave" ]] || clave="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$USUARIO_BD'" | grep -q 1; then
    sudo -u postgres psql -qc "ALTER ROLE $USUARIO_BD WITH LOGIN PASSWORD '$clave'"
  else
    sudo -u postgres psql -qc "CREATE ROLE $USUARIO_BD WITH LOGIN PASSWORD '$clave'"
  fi
  if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$NOMBRE_BD'" | grep -q 1; then
    # template0 + C.UTF-8: la base queda en UTF-8 aunque el clúster existente tenga otra codificación (textos en
    # español con tildes y ñ; SQL_ASCII rompe las búsquedas).
    sudo -u postgres createdb -O "$USUARIO_BD" -E UTF8 -T template0 --locale=C.UTF-8 "$NOMBRE_BD"
  fi
  # Acceso por contraseña desde 127.0.0.1 solo para este usuario y esta base (se agrega una línea, no se reescribe).
  local hba; hba="$(sudo -u postgres psql -tAc 'SHOW hba_file')"
  local regla="host    $NOMBRE_BD    $USUARIO_BD    127.0.0.1/32    scram-sha-256"
  if ! grep -qF "$regla" "$hba"; then
    cp "$hba" "$hba.koape-aguateras.bak"
    sed -i "1i $regla" "$hba"
    systemctl reload postgresql
  fi
  escribir_env DB_MOTOR postgres
  escribir_env DB_NOMBRE "$NOMBRE_BD"
  escribir_env DB_USUARIO "$USUARIO_BD"
  escribir_env DB_CONTRASENA "$clave"
  escribir_env DB_SERVIDOR 127.0.0.1
  escribir_env DB_PUERTO 5432
  ok "Base $NOMBRE_BD lista (usuario $USUARIO_BD; la contraseña queda solo en backend/.env)."
}
