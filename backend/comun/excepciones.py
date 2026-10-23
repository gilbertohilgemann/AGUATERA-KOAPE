"""Formato de error uniforme de la API: `{"detalle": "...", ...}` en castellano."""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .errores import ErrorNegocio


def manejador_excepciones(exc, context):
    if isinstance(exc, ErrorNegocio):
        # Una regla incumplida no es un fallo del servidor: 400 con el mensaje para el usuario.
        return Response({'detalle': str(exc), 'codigo': exc.codigo, **exc.datos}, status=status.HTTP_400_BAD_REQUEST)
    respuesta = exception_handler(exc, context)
    if respuesta is not None and isinstance(respuesta.data, dict) and 'detail' in respuesta.data:
        respuesta.data['detalle'] = respuesta.data.pop('detail')
    return respuesta
