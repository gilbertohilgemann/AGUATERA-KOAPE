"""Registra cada solicitud hecha con una credencial de integración (método, ruta, respuesta, IP, duración)."""
import time

from django.db import DatabaseError
from django.utils import timezone


class MiddlewareRegistroIntegracion:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        inicio = time.monotonic()
        respuesta = self.get_response(request)
        credencial = getattr(request, 'credencial_integracion', None)
        if credencial is not None:
            from .models import CredencialIntegracion, RegistroSolicitudIntegracion
            try:
                RegistroSolicitudIntegracion.objects.create(
                    credencial=credencial, metodo=request.method[:8], ruta=request.get_full_path()[:300],
                    estado=respuesta.status_code, ip=request.META.get('REMOTE_ADDR') or None,
                    duracion_ms=int((time.monotonic() - inicio) * 1000),
                    id_solicitud=str(getattr(request, 'id_solicitud', '') or '')[:64])
                CredencialIntegracion.objects.filter(pk=credencial.pk).update(ultimo_uso_en=timezone.now())
            except DatabaseError:
                pass  # el registro no debe tumbar la respuesta
        return respuesta
