"""Sesión del portal: `Authorization: Portal <token>`. Solo la aceptan las vistas del portal (y nada más la acepta)."""
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

from apps.identidad.tokens import hash_de

from .models import SesionPortal

MENSAJE = 'Sesión vencida: vuelva a ingresar.'


class AutenticacionPortal(BaseAuthentication):
    def authenticate(self, request):
        partes = get_authorization_header(request).split()
        if not partes or partes[0].lower() != b'portal':
            return None
        if len(partes) != 2:
            raise exceptions.AuthenticationFailed(MENSAJE)
        try:
            token = partes[1].decode('ascii')
        except UnicodeDecodeError:
            raise exceptions.AuthenticationFailed(MENSAJE)
        sesion = SesionPortal.objects.select_related('cuenta').filter(clave_hash=hash_de(token)).first()
        if (sesion is None or sesion.revocada_en is not None or sesion.vence_en <= timezone.now()
                or not sesion.cuenta.activa):
            raise exceptions.AuthenticationFailed(MENSAJE)
        return sesion.cuenta, sesion

    def authenticate_header(self, request):
        return 'Portal'
