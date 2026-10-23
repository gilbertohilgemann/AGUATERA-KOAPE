"""
Configuración de Django para Koape Aguateras.

Todo valor sensible o dependiente del entorno se lee desde `backend/.env` (ver `.env.example`).
Decisiones no obvias (detalle en docs/DECISIONES.md):

- UNA sola base central (decisión D2): cada registro de negocio lleva su `institucion` y toda consulta
  se filtra por la institución de la SESIÓN, nunca por un id que mande el navegador.
- SQLite en desarrollo y PostgreSQL en producción (decisión D1); el paso de uno a otro se hace sin
  perder datos desde el panel «Migración de base de datos».
- El usuario es un modelo propio (`identidad.Usuario`) porque el mismo nombre de usuario puede existir
  en dos instituciones distintas.
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
RAIZ_PROYECTO = BASE_DIR.parent

load_dotenv(BASE_DIR / '.env')


def _bool(nombre: str, por_defecto: bool = False) -> bool:
    valor = os.environ.get(nombre)
    if valor is None:
        return por_defecto
    return valor.strip().lower() in {'1', 'true', 'si', 'sí', 'yes', 'on'}


def _lista(nombre: str) -> list[str]:
    return [v.strip() for v in os.environ.get(nombre, '').split(',') if v.strip()]


DEBUG = _bool('DEBUG', True)

SECRET_KEY = os.environ.get('SECRET_KEY', '')
if not SECRET_KEY:
    if DEBUG:
        # Solo para desarrollo local; el instalador genera una clave real en .env.
        SECRET_KEY = 'solo-desarrollo-no-usar-en-produccion'
    else:
        raise ImproperlyConfigured(
            'Falta SECRET_KEY en backend/.env. Con DEBUG=False el sistema no arranca sin ella.'
        )

# Clave para cifrar secretos de integraciones (si falta, se usa SECRET_KEY).
CLAVE_CIFRADO = os.environ.get('CLAVE_CIFRADO', '')

# Desarrollo sin fricción (probar desde el celular u otra PC de la red) vs. producción estricta.
if DEBUG:
    ALLOWED_HOSTS = ['*']
    CORS_ALLOW_ALL_ORIGINS = True
else:
    ALLOWED_HOSTS = _lista('ALLOWED_HOSTS')
    CORS_ALLOWED_ORIGINS = _lista('CORS_ALLOWED_ORIGINS')
    CSRF_TRUSTED_ORIGINS = _lista('CSRF_TRUSTED_ORIGINS')
    SESSION_COOKIE_SECURE = _bool('COOKIES_SEGURAS', True)
    CSRF_COOKIE_SECURE = _bool('COOKIES_SEGURAS', True)

from corsheaders.defaults import default_headers  # noqa: E402

# Identificador de solicitud que puede mandar el frontend (se guarda en la auditoría).
CORS_ALLOW_HEADERS = (*default_headers, 'x-id-solicitud')
CORS_EXPOSE_HEADERS = ['X-Id-Solicitud', 'Content-Disposition']

# Detrás del servidor web (nginx/Caddy) con HTTPS: se confía en X-Forwarded-Proto.
HTTPS = _bool('HTTPS', False)
if HTTPS:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

SECURE_REFERRER_POLICY = 'same-origin'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    # Plataforma y seguridad
    'apps.plataforma',
    'apps.identidad',
    'apps.auditoria',
    # Padrón y territorio (Fase 2)
    'apps.territorio',
    'apps.padron',
    'apps.facturacion',
    'apps.recorridos',
    'apps.lecturas',
    'apps.tarifas',
    'apps.cobranzas',
    'apps.caja',
    'apps.informes',
    'apps.integraciones',
    'apps.portal',
    # Paneles de infraestructura (patrón «sin tabla»)
    'apps.migracion_bd',
    'apps.respaldo',
    'apps.manual',
]

MIDDLEWARE = [
    'comun.middleware.MiddlewareIdSolicitud',
    'apps.integraciones.middleware.MiddlewareRegistroIntegracion',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'configuracion.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'configuracion.wsgi.application'

# --- Datos en disco -------------------------------------------------------------
DIR_DATOS = Path(os.environ.get('DIR_DATOS') or (BASE_DIR / 'datos'))
DIR_RESPALDOS = Path(os.environ.get('DIR_RESPALDOS') or (BASE_DIR / 'respaldos'))
# Archivos privados (fotos de medidores, viviendas, comprobantes): FUERA de media/ y nunca servidos
# por una ruta pública; solo los entregan endpoints que verifican permisos.
DIR_PRIVADO = Path(os.environ.get('DIR_PRIVADO') or (BASE_DIR / 'privado'))
# SQLite no crea carpetas: sin esto, la primera instalación falla con «unable to open database file».
DIR_DATOS.mkdir(parents=True, exist_ok=True)

# --- Base de datos -------------------------------------------------------------------
OPCIONES_SQLITE = {
    'timeout': 20,
    # WAL permite lecturas concurrentes mientras otro proceso escribe.
    'init_command': 'PRAGMA journal_mode=WAL;',
    'transaction_mode': 'IMMEDIATE',
}

DB_MOTOR = os.environ.get('DB_MOTOR', 'sqlite').strip().lower()
if DB_MOTOR in {'postgres', 'postgresql'}:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NOMBRE', 'koape_aguateras'),
            'USER': os.environ.get('DB_USUARIO', ''),
            'PASSWORD': os.environ.get('DB_CONTRASENA', ''),
            'HOST': os.environ.get('DB_SERVIDOR', 'localhost'),
            'PORT': os.environ.get('DB_PUERTO', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': DIR_DATOS / 'aguateras.sqlite3',
            'OPTIONS': OPCIONES_SQLITE,
            # Las pruebas usan un archivo (no memoria): el respaldo y la migración copian el archivo real.
            'TEST': {'NAME': str(DIR_DATOS / 'pruebas.sqlite3')},
        }
    }

AUTH_USER_MODEL = 'identidad.Usuario'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es'
TIME_ZONE = 'America/Asuncion'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CACHES = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['apps.identidad.autenticacion.AutenticacionToken',
                                       'apps.integraciones.autenticacion.AutenticacionIntegracion'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_PAGINATION_CLASS': 'comun.paginacion.PaginacionEstandar',
    'PAGE_SIZE': 50,
    'DEFAULT_THROTTLE_RATES': {
        'ingreso': os.environ.get('LIMITE_INGRESO', '10/min'),
        'contrasena': os.environ.get('LIMITE_CAMBIO_CONTRASENA', '10/hour'),
        'portal_pin': os.environ.get('LIMITE_PIN_PORTAL', '10/hour'),
        'recuperar': os.environ.get('LIMITE_RECUPERAR_CONTRASENA', '10/hour'),
    },
    # Detrás del servidor web (nginx/Caddy) hay 1 proxy: el límite por IP usa la IP real del cliente y no
    # se puede esquivar mandando otro X-Forwarded-For. En desarrollo (sin proxy) queda vacío.
    'NUM_PROXIES': int(os.environ['NUM_PROXIES']) if os.environ.get('NUM_PROXIES', '').strip() else None,
    'EXCEPTION_HANDLER': 'comun.excepciones.manejador_excepciones',
    'UNAUTHENTICATED_USER': None,
}

# --- Parámetros propios de Koape --------------------------------------------------
KOAPE = {
    'VIGENCIA_TOKEN_HORAS': int(os.environ.get('VIGENCIA_TOKEN_HORAS', '12')),
    'INTENTOS_INGRESO_MAXIMOS': int(os.environ.get('INTENTOS_INGRESO_MAXIMOS', '5')),
    'MINUTOS_BLOQUEO_INGRESO': int(os.environ.get('MINUTOS_BLOQUEO_INGRESO', '15')),
    'RESPALDOS_A_CONSERVAR': int(os.environ.get('RESPALDOS_A_CONSERVAR', '4')),
    # Carpeta extra (disco externo / red) donde el respaldo automático deja una copia. Vacío = no copia.
    'DIR_RESPALDOS_COPIA': os.environ.get('DIR_RESPALDOS_COPIA', '').strip(),
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {'format': '{asctime} {levelname} {name}: {message}', 'style': '{'},
    },
    'handlers': {
        'consola': {'class': 'logging.StreamHandler', 'formatter': 'simple'},
    },
    'root': {'handlers': ['consola'], 'level': 'INFO'},
}

# --- Correo (PIN del portal de abonados) ---------------------------------------------
# Configurable (decisión del cliente): con EMAIL_HOST se envía por SMTP; sin él, cada correo queda como archivo en
# datos/correos/ (para probar en la PC sin servidor de correo). Nunca se muestra el PIN en pantalla.
EMAIL_HOST = os.environ.get('EMAIL_HOST', '').strip()
if EMAIL_HOST:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
    EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
    EMAIL_USE_SSL = os.environ.get('EMAIL_USE_SSL', '').lower() in ('1', 'true', 'si', 'sí')
    EMAIL_USE_TLS = not EMAIL_USE_SSL and os.environ.get('EMAIL_USE_TLS', '1').lower() in ('1', 'true', 'si', 'sí')
    EMAIL_TIMEOUT = 20
else:
    EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
    EMAIL_FILE_PATH = DIR_DATOS / 'correos'
DEFAULT_FROM_EMAIL = os.environ.get('CORREO_REMITENTE', 'Koape Aguateras <no-responder@koapesystem.com>')

