"""
Identificador de solicitud.

Cada pedido recibe un id (el que mande el frontend en `X-Id-Solicitud`, si es válido, o uno nuevo).
Se guarda en la auditoría y vuelve en la respuesta: así un error que ve el usuario se puede ubicar
en los registros sin adivinar.
"""
import re
import uuid

PATRON_ID = re.compile(r'^[A-Za-z0-9-]{8,64}$')


class MiddlewareIdSolicitud:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        propuesto = request.headers.get('X-Id-Solicitud', '')
        request.id_solicitud = propuesto if PATRON_ID.match(propuesto) else uuid.uuid4().hex
        respuesta = self.get_response(request)
        respuesta['X-Id-Solicitud'] = request.id_solicitud
        return respuesta
