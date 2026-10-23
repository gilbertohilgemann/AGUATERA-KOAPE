"""Administración de credenciales de integración (permiso `integraciones.administrar`)."""
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identidad.models import Permiso
from apps.identidad.permisos import RequierePermiso
from comun.vistas import VistaInstitucional

from . import servicios
from .autenticacion import PERMISOS_ASIGNABLES
from .models import CredencialIntegracion


class CredencialSerializer(serializers.ModelSerializer):
    creada_por = serializers.CharField(source='creada_por.nombre_usuario', read_only=True)
    revocada_por = serializers.CharField(source='revocada_por.nombre_usuario', default=None, read_only=True)
    usos_30_dias = serializers.SerializerMethodField()

    class Meta:
        model = CredencialIntegracion
        fields = ['prefijo', 'nombre', 'permisos', 'limite_por_minuto', 'expira_en', 'activa', 'creada_por', 'creado_en',
                  'revocada_por', 'revocada_en', 'motivo_revocacion', 'ultimo_uso_en', 'usos_30_dias']
        read_only_fields = fields

    def get_usos_30_dias(self, c):
        from datetime import timedelta

        from django.utils import timezone
        return c.registros.filter(fecha_hora__gte=timezone.now() - timedelta(days=30)).count()


class NuevaCredencialSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=120)
    permisos = serializers.ListField(child=serializers.CharField(max_length=60), min_length=1)
    limite_por_minuto = serializers.IntegerField(min_value=1, max_value=600, default=60)
    expira_en = serializers.DateTimeField(required=False, allow_null=True, default=None)


class CredencialVista(VistaInstitucional, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'integraciones.administrar'
    modelo = CredencialIntegracion
    serializer_class = CredencialSerializer
    lookup_field = 'prefijo'
    lookup_value_regex = r'[a-z0-9]{8}'
    pagination_class = None

    def get_queryset(self):
        return self.consulta_base().select_related('creada_por', 'revocada_por')

    def create(self, request):
        s = NuevaCredencialSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        credencial, clave = servicios.crear(institucion=self.institucion, usuario=request.user, request=request,
                                            **s.validated_data)
        return Response({**CredencialSerializer(credencial).data, 'clave': clave}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def revocar(self, request, **kwargs):
        credencial = servicios.revocar(self.get_object(), motivo=request.data.get('motivo', ''), usuario=request.user,
                                       request=request)
        return Response(CredencialSerializer(credencial).data)

    @action(detail=True, methods=['get'])
    def registro(self, request, **kwargs):
        credencial = self.get_object()
        return Response([{'fecha_hora': r.fecha_hora, 'metodo': r.metodo, 'ruta': r.ruta, 'estado': r.estado,
                          'ip': r.ip, 'duracion_ms': r.duracion_ms} for r in credencial.registros.all()[:200]])


class PermisosAsignablesVista(APIView):
    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'integraciones.administrar'

    def get(self, request):
        descripciones = dict(Permiso.objects.filter(codigo__in=PERMISOS_ASIGNABLES).values_list('codigo', 'descripcion'))
        return Response([{'codigo': c, 'descripcion': descripciones.get(c, c)} for c in PERMISOS_ASIGNABLES])
