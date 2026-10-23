"""
API de tarifas (`tarifas.gestionar`; lectura también con `liquidaciones.consultar`) y de liquidaciones
(`liquidaciones.consultar`; liquidar pendientes con `tarifas.gestionar`).
"""
from django.db.models import Prefetch, Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identidad.permisos import RequierePermiso
from apps.recorridos.models import PERIODO
from comun.codigos import VistaPorCode, normalizar_code
from comun.vistas import VistaInstitucional, institucion_de

from . import servicios
from .models import ConceptoTarifa, Liquidacion, Tarifa, VersionTarifa
from .serializadores import (LiquidacionSerializer, SimularSerializer, TarifaSerializer, VersionEntradaSerializer,
                             VersionSerializer)


class TarifaVista(VistaPorCode, VistaInstitucional, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                  viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'tarifas.gestionar'
    permisos_lectura = ('liquidaciones.consultar', 'padron.conexiones', 'padron.consultar')
    acciones_de_lectura = ('simular',)  # simular no guarda nada
    modelo = Tarifa
    serializer_class = TarifaSerializer
    pagination_class = None

    def get_queryset(self):
        conceptos = ConceptoTarifa.objects.order_by('orden', 'id')
        return self.consulta_base().prefetch_related(
            Prefetch('versiones', queryset=VersionTarifa.objects.prefetch_related(Prefetch('conceptos', queryset=conceptos))))

    def get_serializer_context(self):
        return {**super().get_serializer_context(), 'institucion': self.institucion}

    def _datos(self, instancia=None):
        s = TarifaSerializer(instancia, data=self.request.data, partial=instancia is not None,
                             context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        return dict(s.validated_data)

    def _respuesta(self, tarifa, codigo=status.HTTP_200_OK):
        return Response(TarifaSerializer(self.get_queryset().get(pk=tarifa.pk)).data, status=codigo)

    def create(self, request):
        tarifa = servicios.crear_tarifa(institucion=self.institucion, datos=self._datos(), request=request)
        return self._respuesta(tarifa, status.HTTP_201_CREATED)

    def partial_update(self, request, **kwargs):
        tarifa = self.get_object()
        servicios.actualizar_tarifa(tarifa, self._datos(tarifa), request=request)
        return self._respuesta(tarifa)

    @action(detail=True, methods=['post'])
    def versiones(self, request, **kwargs):
        """Crea una versión nueva (vigente desde un período)."""
        tarifa = self.get_object()
        datos = VersionEntradaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        d = datos.validated_data
        servicios.crear_version(tarifa, vigente_desde=d['vigente_desde'], observaciones=d['observaciones'],
                                conceptos=[dict(c) for c in d['conceptos']], request=request)
        return self._respuesta(tarifa, status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], url_path=r'versiones/(?P<periodo>\d{4}-\d{2})')
    def version(self, request, periodo=None, **kwargs):
        """Modifica una versión que todavía no se usó (o solo sus observaciones si ya se usó)."""
        tarifa = self.get_object()
        version = tarifa.versiones.filter(vigente_desde=periodo).first()
        if version is None:
            raise NotFound('No existe esa versión.')
        conceptos = None
        if 'conceptos' in request.data:
            datos = VersionEntradaSerializer(data={**request.data, 'vigente_desde': periodo})
            datos.is_valid(raise_exception=True)
            conceptos = [dict(c) for c in datos.validated_data['conceptos']]
        servicios.actualizar_version(version, conceptos=conceptos, observaciones=request.data.get('observaciones'),
                                     request=request)
        return self._respuesta(tarifa)

    @action(detail=True, methods=['post'])
    def simular(self, request, **kwargs):
        """Calcula el importe para un consumo, sin guardar nada (para probar la tarifa)."""
        tarifa = self.get_object()
        datos = SimularSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        return Response(servicios.simular(tarifa, **datos.validated_data))


class LiquidacionVista(VistaInstitucional, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'tarifas.gestionar'
    permisos_lectura = ('liquidaciones.consultar',)
    modelo = Liquidacion
    serializer_class = LiquidacionSerializer
    lookup_field = 'numero'
    lookup_value_regex = r'[Ll][Qq]-[A-Za-z0-9]+'

    def get_object(self):
        self.kwargs['numero'] = normalizar_code(self.kwargs['numero'])
        return super().get_object()

    def get_queryset(self):
        consulta = (self.consulta_base().select_related('lectura', 'conexion__cliente', 'tarifa', 'version', 'anulada_por')
                    .prefetch_related('lineas'))
        if self.action != 'list':
            return consulta
        p = self.request.query_params
        if p.get('periodo'):
            consulta = consulta.filter(periodo=p['periodo'])
        if p.get('estado'):
            consulta = consulta.filter(estado=p['estado'])
        for parametro, campo in (('conexion', 'conexion__Code'), ('tarifa', 'tarifa__Code'),
                                 ('lectura', 'lectura__comprobante')):
            if p.get(parametro):
                consulta = consulta.filter(**{campo: normalizar_code(p[parametro])})
        if p.get('buscar'):
            t = p['buscar'].strip()
            consulta = consulta.filter(Q(numero__icontains=t) | Q(conexion__Code__icontains=t)
                                       | Q(conexion__cliente__nombre__icontains=t))
        return consulta.order_by('-periodo', '-creado_en')

    @action(detail=False, methods=['post'], url_path='liquidar-pendientes')
    def liquidar_pendientes(self, request):
        periodo = (request.data.get('periodo') or '').strip() or None
        if periodo:
            PERIODO(periodo)
        return Response(servicios.liquidar_pendientes(self.institucion, periodo=periodo, request=request))


class ResumenLiquidacionVista(APIView):
    """Totales del período y lecturas confirmadas sin liquidar (ej. faltaba la tarifa)."""

    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'liquidaciones.consultar'
    permisos_lectura = ('tarifas.gestionar',)

    def get(self, request):
        from django.db.models import Count, Sum
        from apps.lecturas.models import Lectura
        institucion = institucion_de(request)
        periodo = request.query_params.get('periodo', '')
        vigentes = Liquidacion.objects.de(institucion).filter(estado=Liquidacion.Estado.VIGENTE)
        if periodo:
            vigentes = vigentes.filter(periodo=periodo)
        totales = vigentes.aggregate(cantidad=Count('id'), consumo=Sum('consumo'), exento=Sum('subtotal_exento'),
                                     gravado5=Sum('subtotal_iva5'), gravado10=Sum('subtotal_iva10'), iva5=Sum('iva5'),
                                     iva10=Sum('iva10'), total=Sum('total'))
        sin_liquidar = (Lectura.objects.de(institucion).filter(estado=Lectura.Estado.CONFIRMADA)
                        .exclude(liquidaciones__estado=Liquidacion.Estado.VIGENTE))
        if periodo:
            sin_liquidar = sin_liquidar.filter(periodo=periodo)
        return Response({**{k: v or 0 for k, v in totales.items()}, 'sin_liquidar': sin_liquidar.count()})
