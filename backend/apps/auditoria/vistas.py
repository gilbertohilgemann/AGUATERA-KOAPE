from django.utils.dateparse import parse_date
from rest_framework import mixins, serializers, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.identidad.permisos import RequierePermiso
from comun.vistas import VistaInstitucional

from .models import RegistroAuditoria


def _fecha(valor):
    try:
        return parse_date(valor or '')
    except ValueError:
        return None


class RegistroAuditoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegistroAuditoria
        fields = ['id', 'ocurrido_en', 'usuario_nombre', 'accion', 'entidad', 'entidad_id', 'resultado',
                  'motivo', 'antes', 'despues', 'detalle', 'ip', 'id_solicitud']


class RegistroAuditoriaVista(VistaInstitucional, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                             viewsets.GenericViewSet):
    """Solo lectura y solo la institución de la sesión: la auditoría no se edita ni se borra."""

    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'auditoria.consultar'
    serializer_class = RegistroAuditoriaSerializer
    modelo = RegistroAuditoria

    def get_queryset(self):
        consulta = self.consulta_base()
        p = self.request.query_params
        desde, hasta = _fecha(p.get('desde')), _fecha(p.get('hasta'))
        if desde:
            consulta = consulta.filter(ocurrido_en__date__gte=desde)
        if hasta:
            consulta = consulta.filter(ocurrido_en__date__lte=hasta)
        if p.get('accion'):
            consulta = consulta.filter(accion=p['accion'])
        if p.get('usuario'):
            consulta = consulta.filter(usuario_nombre__icontains=p['usuario'])
        if p.get('entidad'):
            consulta = consulta.filter(entidad=p['entidad'])
        if p.get('resultado'):
            consulta = consulta.filter(resultado=p['resultado'])
        return consulta
