"""
Chequeo de seguridad y respaldos de la instalación.

Solo mira la configuración y los usuarios de la plataforma: no abre datos de las instituciones.
Cada hallazgo es (nivel, mensaje, qué hacer); nivel ∈ {'grave', 'aviso', 'ok'}.
"""
import os
from datetime import datetime, timedelta, timezone as zona
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

CONTRASENA_DE_FABRICA = 'Koape.Admin.2026'
CLAVE_DESARROLLO = 'solo-desarrollo-no-usar-en-produccion'


def _ultimo_respaldo():
    carpeta = Path(settings.DIR_RESPALDOS)
    archivos = sorted(carpeta.glob('*.zip'), key=lambda p: p.stat().st_mtime, reverse=True) if carpeta.exists() else []
    return archivos[0] if archivos else None


def revisar() -> list[dict]:
    hallazgos = []

    def agregar(nivel, mensaje, accion=''):
        hallazgos.append({'nivel': nivel, 'mensaje': mensaje, 'accion': accion})

    produccion = os.environ.get('MODO', 'desarrollo').strip().lower() == 'produccion'
    if settings.DEBUG:
        agregar('grave' if produccion else 'aviso', 'El servidor está en modo desarrollo (DEBUG=True): muestra detalles de errores y acepta cualquier origen.',
                'Para uso real: DEBUG=False y MODO=produccion en backend/.env (el instalador del servidor lo deja así).')
    else:
        agregar('ok', 'Modo producción (DEBUG=False).')

    clave = settings.SECRET_KEY or ''
    if clave == CLAVE_DESARROLLO or len(clave) < 50:
        agregar('grave', 'SECRET_KEY falta o es débil.', 'Vuelva a ejecutar el instalador: genera una clave aleatoria.')
    if not settings.CLAVE_CIFRADO:
        agregar('aviso', 'CLAVE_CIFRADO vacía: las claves de integraciones se cifran con SECRET_KEY.',
                'No cambie SECRET_KEY sin antes copiar su valor a CLAVE_CIFRADO.')

    Usuario = get_user_model()
    for usuario in Usuario.objects.filter(institucion__isnull=True, is_superuser=True, is_active=True):
        if usuario.check_password(CONTRASENA_DE_FABRICA):
            agregar('grave', f'El administrador de la plataforma «{usuario.nombre_usuario}» usa la contraseña de fábrica.',
                    'Cámbiela desde el panel (Usuarios → su usuario → Restablecer contraseña) o en ADMIN_PLATAFORMA_CONTRASENA (backend/.env) y vuelva a correr el instalador.')

    if getattr(settings, 'HTTPS', False):
        agregar('ok', 'HTTPS activo: las contraseñas y los datos viajan cifrados por la red.')
    else:
        agregar('aviso', 'Sin HTTPS: en la red local las contraseñas viajan sin cifrar.',
                'En el servidor, scripts/servidor/instalar_fedora.sh configura HTTPS con Let'"'"'s Encrypt.')
    if not settings.DEBUG and '*' in settings.ALLOWED_HOSTS:
        agregar('grave', 'ALLOWED_HOSTS acepta cualquier nombre (*).', 'Liste solo los nombres/IP del servidor.')

    ultimo = _ultimo_respaldo()
    if ultimo is None:
        agregar('grave', 'No hay ningún respaldo en este servidor.', 'Ejecute start respaldo-programar (respaldo diario).')
    else:
        hecho = datetime.fromtimestamp(ultimo.stat().st_mtime, tz=zona.utc)
        edad = timezone.now() - hecho
        if edad > timedelta(days=2):
            agregar('aviso', f'El último respaldo tiene {edad.days} días ({ultimo.name}).',
                    'Revise la tarea programada (start respaldo-programar) o corra start respaldo.')
        else:
            agregar('ok', f'Último respaldo: {timezone.localtime(hecho):%d/%m/%Y %H:%M}.')
    copia = settings.KOAPE.get('DIR_RESPALDOS_COPIA')
    if not copia:
        agregar('aviso', 'Los respaldos quedan solo en este mismo disco: si se rompe la computadora se pierden con ella.',
                'Configure DIR_RESPALDOS_COPIA (disco externo o carpeta de red) en backend/.env.')
    elif not Path(copia).is_dir():
        agregar('aviso', f'La carpeta de copia de respaldos no está disponible: {copia}.', 'Conecte el disco o revise la ruta de red.')
    else:
        agregar('ok', f'Se deja copia de los respaldos en {copia}.')
    return hallazgos
