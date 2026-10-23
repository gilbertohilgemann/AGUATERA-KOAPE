"""
Autenticación DRF por token.

Del token salen el usuario y la INSTITUCIÓN de la sesión (`request.institucion`). Ningún dato que
mande el navegador puede cambiarla. Se verifica en cada solicitud: token vigente, usuario activo,
institución activa y que el usuario siga perteneciendo a esa institución.
"""
from datetime import timedelta

from django.db import OperationalError
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

from .models import TokenSesion
from .tokens import hash_de

PALABRA_CLAVE = b'token'
INTERVALO_REGISTRO_USO = timedelta(minutes=5)
MENSAJE = 'Sesión inválida o vencida.'


class AutenticacionToken(BaseAuthentication):
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

        token = (
            TokenSesion.objects.select_related('usuario', 'institucion')
            .filter(clave_hash=hash_de(clave))
            .first()
        )
        ahora = timezone.now()
        if (
            token is None
            or token.revocado_en is not None
            or token.expira_en <= ahora
            or not token.usuario.is_active
            or token.usuario.institucion_id != token.institucion_id
        ):
            raise exceptions.AuthenticationFailed(MENSAJE)

        if not token.institucion.esta_activa:
            raise exceptions.AuthenticationFailed('La institución está suspendida. Contacte al administrador de la plataforma.')

        if token.ultimo_uso is None or ahora - token.ultimo_uso > INTERVALO_REGISTRO_USO:
            try:
                TokenSesion.objects.filter(pk=token.pk).update(ultimo_uso=ahora)
            except OperationalError:  # base ocupada: el «último uso» puede esperar
                pass

        # Única fuente de la institución de la solicitud.
        request._request.institucion = token.institucion
        return token.usuario, token

    def authenticate_header(self, request):
        return 'Token'
