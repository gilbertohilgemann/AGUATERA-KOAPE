# Despliegue en el VPS (Fedora Cloud)

Guía paso a paso para poner Koape Aguateras en el servidor. Los comandos van **como root** en el VPS, salvo que se
indique otra cosa. El instalador nunca asume que el servidor está vacío: si ya hay otros sistemas (por ejemplo Koape
Hotel-Restaurante), agrega este como **un sitio más** del servidor web que exista (nginx, Caddy o Apache) y crea en
PostgreSQL **solo** su propio usuario y su base, sin tocar los demás.

## Lo que hace falta antes

| Dato | Para qué | Dónde se carga |
|---|---|---|
| IP del VPS y acceso SSH como root | Instalar | — |
| Dominio (por defecto `aguateras.koapesystem.com`) con un registro **A** apuntando a la IP del VPS | HTTPS (Let's Encrypt) | Panel DNS del dominio |
| Correo para Let's Encrypt (avisos de vencimiento) | HTTPS | Al instalar |
| Servidor de correo SMTP (servidor, puerto, usuario, contraseña) | PIN del portal y «¿Olvidó su contraseña?» | `configurar_correo.sh` (paso 5), cuando lo tenga |
| Acceso al repositorio privado de GitHub | Bajar el código y actualizarlo | Clave de despliegue (paso 2) |

Puertos 80 y 443 abiertos (el instalador los habilita en `firewalld` si está activo; si el proveedor del VPS tiene
un firewall propio, ábralos ahí también).

## Camino rápido: un solo script (pasos 1 a 4)

`scripts/servidor/preparar_vps.sh` hace los pasos 1 a 4 de corrido en un VPS nuevo: crea el usuario `webuser` y su
carpeta, instala git, genera la clave de solo lectura del VPS, se la muestra y **espera** a que la cargue en GitHub
(Deploy keys), prueba el acceso, baja el código a `/home/webuser/AGUATERA-KOAPE` e instala. Como el repositorio es
privado, el script se copia al VPS desde la PC (o se pega con `cat > preparar_vps.sh`):

```powershell
# en la PC
scp C:\proyectos_claude\AGUATERA-KOAPE\scripts\servidor\preparar_vps.sh root@IP-DEL-VPS:/root/
```
```bash
# en el VPS, como root
bash /root/preparar_vps.sh gilbertohilgemann aguateras.koapesystem.com correo@koapesystem.com
```

Se puede volver a ejecutar: reutiliza el usuario, la clave y el código que ya existan. Los pasos siguientes explican
lo mismo a mano.

## 1. Preparar el usuario de la aplicación

El sistema corre con el usuario `webuser` (sin contraseña: nadie ingresa con él). Si no existe:

```bash
useradd -m webuser
dnf install -y git
```

## 2. Acceso de solo lectura al repositorio (clave de despliegue)

```bash
sudo -u webuser ssh-keygen -t ed25519 -N "" -C "vps-aguateras" -f /home/webuser/.ssh/aguateras_github
cat /home/webuser/.ssh/aguateras_github.pub
```

Copie la línea que muestra y en GitHub: repositorio **AGUATERA-KOAPE → Settings → Deploy keys → Add deploy key**
(título «VPS», **sin** marcar «Allow write access»). Después:

```bash
sudo -u webuser tee -a /home/webuser/.ssh/config >/dev/null <<'CONF'
Host github-aguateras
    HostName github.com
    User git
    IdentityFile ~/.ssh/aguateras_github
    IdentitiesOnly yes
CONF
chmod 600 /home/webuser/.ssh/config
sudo -u webuser ssh -o StrictHostKeyChecking=accept-new -T github-aguateras   # «successfully authenticated» = bien
```

## 3. Bajar el código

```bash
sudo -u webuser git clone github-aguateras:<usuario-de-github>/AGUATERA-KOAPE.git /home/webuser/AGUATERA-KOAPE
```

## 4. Instalar

```bash
bash /home/webuser/AGUATERA-KOAPE/scripts/servidor/instalar_fedora.sh aguateras.koapesystem.com correo@koapesystem.com
```

Muestra lo que va a hacer y pide confirmación. Instala lo necesario (Python, Node, PostgreSQL si no está), genera
las claves secretas, crea la base `koape_aguateras` en UTF-8, compila el frontend, crea el servicio
`koape-aguateras` (backend en `127.0.0.1`, en un puerto libre desde 8115), el respaldo diario (03:20, se conservan
4), el sitio web y el certificado HTTPS.

Al final muestra la dirección del sistema y la **contraseña del panel de la plataforma** (`/admin/`), generada al
azar y guardada en `backend/.env` (solo la leen `webuser` y root). Guárdela y cámbiela al ingresar.

Si el DNS todavía no apuntaba al VPS, el certificado falla sin romper nada; cuando apunte:

```bash
bash /home/webuser/AGUATERA-KOAPE/scripts/servidor/https.sh
```

## 5. Correo (cuando tenga los datos del SMTP)

```bash
bash /home/webuser/AGUATERA-KOAPE/scripts/servidor/configurar_correo.sh
```

Pregunta servidor, seguridad (tls/ssl), puerto, usuario, contraseña y remitente; los guarda en `backend/.env`,
reinicia el backend y ofrece enviar un correo de prueba. Con Gmail o Google Workspace se usa una **contraseña de
aplicación** (no la contraseña normal). Mientras no se configure, los correos quedan como archivos en
`backend/datos/correos/` (nadie los recibe).

## 6. Primeros pasos en el sistema

1. `https://<dominio>/admin/` con el usuario de la plataforma: crear cada institución (código, datos fiscales,
   modalidad de facturación) con su administrador inicial. Para el portal de abonados, marcar «Portal de abonados»
   en la institución (o lo hace su administrador desde el menú **Institución**).
2. `https://<dominio>/` con el código de la institución y su administrador: cargar usuarios (con su **correo**, para
   que puedan recuperar la contraseña), roles, zonas, tarifas, puntos de expedición, padrón, etc.
3. Los cobradores instalan la aplicación desde el navegador del celular en `https://<dominio>/` (con HTTPS
   funcionan el GPS y la instalación).
4. Los abonados consultan en `https://<dominio>/portal`.

## Actualizar a una versión nueva

```bash
bash /home/webuser/AGUATERA-KOAPE/scripts/servidor/actualizar.sh
```

Baja lo último del repositorio, instala dependencias, aplica las migraciones, recompila el frontend y reinicia. Los
datos no se tocan. Conviene hacerlo fuera del horario de cobro (el backend se reinicia unos segundos).

## Respaldos

- Automático todos los días a las 03:20 (`systemctl list-timers koape-aguateras-respaldo.timer`). Se guardan en
  `backend/respaldos/` (los últimos 4). **Copie periódicamente esos archivos fuera del VPS.**
- Manual: desde el panel de la plataforma (**Respaldo**) o `sudo -u webuser backend/venv/bin/python manage.py respaldar`.
- Restaurar: `bash /home/webuser/AGUATERA-KOAPE/scripts/servidor/restaurar.sh <archivo.zip>` (guarda antes un
  respaldo de lo actual).

## Otros comandos

| Qué | Comando |
|---|---|
| Estado del backend | `systemctl status koape-aguateras` |
| Registro de errores | `journalctl -u koape-aguateras -n 100` |
| Reiniciar | `systemctl restart koape-aguateras` |
| Cambiar de dominio | `bash scripts/servidor/cambiar_dominio.sh nuevo.dominio.com` |
| Reintentar HTTPS | `bash scripts/servidor/https.sh` |

## Notas de seguridad

- `backend/.env` tiene las claves (Django, cifrado, base, SMTP): permisos 600, nunca va al repositorio.
- La clave `CLAVE_CIFRADO` cifra secretos guardados en la base (p. ej. credenciales de proveedores): si se pierde,
  esos datos no se pueden leer. Inclúyala en su copia de seguridad del `.env`, aparte de los respaldos.
- La clave de despliegue de GitHub es de solo lectura y sirve solo para este repositorio.
- El backend escucha solo en `127.0.0.1`; desde internet se entra únicamente por el servidor web con HTTPS.
- `manage.py check --deploy` avisa de HSTS y de redirección a HTTPS: los hace el servidor web (Caddy agrega HSTS;
  con nginx/Apache, certbot configura la redirección).
