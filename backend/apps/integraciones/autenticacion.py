"""
Autenticación de aplicaciones externas: `Authorization: Clave kpa_<identificador>_<secreto>`.

La credencial se presenta como un «usuario» de solo lectura con los permisos que le dio el administrador: así usa
EXACTAMENTE las mismas vistas, filtros por institución y reglas que la aplicación (no se duplica lógica).
"""
import time

from django.core.cache import cache
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.permissions import SAFE_METHODS

from apps.identidad.tokens import hash_de

from .models import CredencialIntegracion

PALABRA_CLAVE = b'clave'
MENSAJE = 'Credencial de integración inválida, vencida o revocada.'

# Permisos que se pueden dar a una credencial (todos de consulta; la credencial nunca escribe).
PERMISOS_ASIGNABLES = ['padron.consultar', 'mapa.ver', 'lecturas.consultar', 'liquidaciones.consultar',
                       'facturacion.consultar', 'cobranzas.consultar', 'gastos.consultar', 'caja.supervisar']


class UsuarioIntegracion:
    """Identidad de una credencial dentro de una solicitud (no es un usuario de la base)."""

    es_integracion = True
    is_authenticated = True
    is_active = True
    is_anonymous = False
    is_superuser = False
    es_admin_institucion = False
    debe_cambiar_contrasena = False
    pk = None
    id = None

    def __init__(self, credencial):
        self.credencial = credencial
        self.institucion = credencial.institucion
        self.institucion_id = credencial.institucion_id
        self.nombre_usuario = f'api:{credencial.prefijo}'
        self.identificador = f'{credencial.institucion.codigo}/api:{credencial.prefijo}'
        self.nombre = credencial.nombre
        self.permisos = set(credencial.permisos) & set(PERMISOS_ASIGNABLES)

    def __str__(self):
        return self.identificador


class AutenticacionIntegracion(BaseAuthentication):
    def authenticate(self, request):
        partes = get_authorization_header(request).split()
        if not partes or partes[0].lower() != PALABRA_CLAVE:
            return None
        if len(partes) != 2:
            raise exceptions.AuthenticationFailed(MENSAJE)
        try:
            clave = partes[1].decode('ascii')
        except UnicodeDecodeError:
            raise exceptions.AuthenticationFailed(MENSAJE)
        credencial = (CredencialIntegracion.objects.select_related('institucion')
                      .filter(clave_hash=hash_de(clave)).first())
        ahora = timezone.now()
        if credencial is not None:
            # Desde aquí la solicitud queda registrada (middleware), aunque se rechace (ej. clave revocada o vencida).
            request._request.credencial_integracion = credencial
        if (credencial is None or not credencial.activa or (credencial.expira_en and credencial.expira_en <= ahora)
                or not credencial.institucion.esta_activa):
            raise exceptions.AuthenticationFailed(MENSAJE)
        if request.method not in SAFE_METHODS:
            raise exceptions.PermissionDenied('Las credenciales de integración son de solo lectura en esta versión.')
        ruta = request._request.path_info  # sin el prefijo de publicación (si el sistema corre bajo /algo/)
        if ruta.startswith('/api/v1/auth/') or ruta.startswith('/api/v1/integraciones/'):
            raise exceptions.PermissionDenied('Esta ruta no está disponible para integraciones.')
        self._limitar(credencial)
        request._request.institucion = credencial.institucion
        return UsuarioIntegracion(credencial), credencial

    @staticmethod
    def _limitar(credencial):
        minuto = int(time.time() // 60)
        llave = f'integracion:{credencial.pk}:{minuto}'
        cache.add(llave, 0, 120)
        try:
            usadas = cache.incr(llave)
        except ValueError:
            cache.set(llave, 1, 120)
            usadas = 1
        if usadas > credencial.limite_por_minuto:
            raise exceptions.Throttled(wait=60 - int(time.time()) % 60,
                                       detail=f'Límite de {credencial.limite_por_minuto} solicitudes por minuto.')

    def authenticate_header(self, request):
        return 'Clave'
