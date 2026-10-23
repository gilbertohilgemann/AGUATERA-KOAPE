"""API de pagos y recibos (Fase 6). Las reglas están en `servicios.py`."""
import re

from django.db.models import Prefetch, Q
from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditoria.servicios import registrar
from apps.identidad.permisos import RequierePermiso
from apps.padron.models import Cliente
from comun.codigos import VistaPorCode, normalizar_code
from comun.vistas import VistaInstitucional, institucion_de

from . import servicios
from .models import AplicacionPago, FormaPago, Pago, Recibo
from .pdf import generar_pdf_recibo
from .serializadores import EmitirReciboSerializer, FormaPagoSerializer, PagoSerializer, ReciboSerializer

LECTURA = ('cobranzas.consultar', 'cobranzas.anular')
APLICACIONES = Prefetch('pago__aplicaciones',
                        queryset=AplicacionPago.objects.select_related('factura__punto').order_by('pk'))


class FormaPagoVista(VistaPorCode, VistaInstitucional, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                     viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'cobranzas.formas_pago'
    permisos_lectura = ('cobranzas.registrar', 'cobranzas.consultar', 'cobranzas.anular', 'facturacion.emitir')
    modelo = FormaPago
    serializer_class = FormaPagoSerializer
    pagination_class = None

    def get_serializer_context(self):
        return {**super().get_serializer_context(), 'institucion': self.institucion}

    def get_queryset(self):
        consulta = self.consulta_base()
        if self.action == 'list' and self.request.query_params.get('activas') == '1':
            consulta = consulta.filter(activa=True)
        return consulta

    def create(self, request):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        forma = s.save(institucion=self.institucion)
        registrar('forma_pago_creada', request=request, entidad='forma_pago', entidad_id=forma.Code, despues=s.data)
        return Response(self.get_serializer(forma).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, **kwargs):
        forma = self.get_object()
        antes = self.get_serializer(forma).data
        s = self.get_serializer(forma, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        registrar('forma_pago_modificada', request=request, entidad='forma_pago', entidad_id=forma.Code, antes=antes,
                  despues=s.data)
        return Response(s.data)


class EstadoCuentaVista(APIView):
    """Lo que el cliente debe a crédito, factura por factura (la vencida más antigua primero), para cobrar."""

    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'cobranzas.registrar'
    permisos_lectura = LECTURA

    def get(self, request):
        institucion = institucion_de(request)
        cliente = Cliente.objects.de(institucion).filter(Code=normalizar_code(request.query_params.get('cliente'))).first()
        if cliente is None:
            raise NotFound('No existe ese cliente.')
        facturas = list(servicios.facturas_con_saldo(institucion, cliente))
        return Response({
            'cliente': {'Code': cliente.Code, 'nombre': cliente.nombre, 'documento': cliente.documento},
            'facturas': [{'referencia': f.referencia, 'numero': f.numero_impreso, 'fecha_emision': f.fecha_emision,
                          'fecha_vencimiento': f.fecha_vencimiento, 'total': f'{f.total:.2f}',
                          'pagado': f'{f.pagado:.2f}', 'saldo': f'{f.saldo:.2f}', 'estado_cobro': servicios.estado_cobro(f, f.saldo)} for f in facturas],
            'total_saldo': f'{sum((f.saldo for f in facturas), servicios.CERO):.2f}',
            'aplicacion_pagos': institucion.aplicacion_pagos,
            'formas_pago': FormaPagoSerializer(FormaPago.objects.de(institucion).filter(activa=True), many=True).data,
        })


class ReciboVista(VistaInstitucional, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Recibos de cobro. Se buscan por su número (`recibos/0000012/`)."""

    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'cobranzas.registrar'
    permisos_lectura = LECTURA
    modelo = Recibo
    serializer_class = ReciboSerializer
    lookup_field = 'numero'
    lookup_value_regex = r'\d{1,10}'

    def check_permissions(self, request):
        if getattr(self, 'action', None) == 'anular':
            self.permiso_requerido = 'cobranzas.anular'
        super().check_permissions(request)

    def get_object(self):
        self.kwargs['numero'] = int(self.kwargs['numero'])
        return super().get_object()

    def get_serializer_context(self):
        return {**super().get_serializer_context(), 'institucion': self.institucion}

    def get_queryset(self):
        consulta = (self.consulta_base().select_related('cliente', 'pago__forma_pago', 'pago__usuario', 'anulado_por')
                    .prefetch_related(APLICACIONES))
        if self.action != 'list':
            return consulta
        p = self.request.query_params
        if p.get('estado'):
            consulta = consulta.filter(estado=p['estado'])
        if p.get('cliente'):
            consulta = consulta.filter(cliente__Code=normalizar_code(p['cliente']))
        if p.get('forma_pago'):
            consulta = consulta.filter(pago__forma_pago__Code=normalizar_code(p['forma_pago']))
        if p.get('desde'):
            consulta = consulta.filter(fecha_hora__date__gte=p['desde'])
        if p.get('hasta'):
            consulta = consulta.filter(fecha_hora__date__lte=p['hasta'])
        if p.get('buscar'):
            t = p['buscar'].strip()
            filtro = Q(cliente_nombre__icontains=t) | Q(cliente_documento__icontains=t) | Q(cliente__Code__iexact=t)
            if re.fullmatch(r'\d{1,10}', t):
                filtro |= Q(numero=int(t))
            consulta = consulta.filter(filtro)
        return consulta.order_by('-numero')

    def _respuesta(self, recibo, codigo=status.HTTP_200_OK):
        self.action = 'retrieve'
        return Response(ReciboSerializer(self.get_queryset().get(pk=recibo.pk)).data, status=codigo)

    def create(self, request):
        s = EmitirReciboSerializer(data=request.data, context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        d = s.validated_data
        recibo = servicios.emitir_recibo(
            institucion=self.institucion, cliente=d['cliente'], importe=d['importe'], forma_pago=d['forma_pago'],
            clave=d['clave'], aplicaciones=d['aplicaciones'], referencia_externa=d['referencia_externa'],
            observaciones=d['observaciones'], usuario=request.user, request=request)
        return self._respuesta(recibo, status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def pdf(self, request, **kwargs):
        recibo = self.get_object()
        respuesta = HttpResponse(generar_pdf_recibo(recibo), content_type='application/pdf')
        respuesta['Content-Disposition'] = f'inline; filename="recibo-{recibo.numero_impreso}.pdf"'
        respuesta['Cache-Control'] = 'private, no-store'
        return respuesta

    @action(detail=True, methods=['post'])
    def anular(self, request, **kwargs):
        recibo = self.get_object()
        servicios.anular_recibo(recibo, motivo=request.data.get('motivo', ''), usuario=request.user, request=request)
        return self._respuesta(recibo)


class PagoVista(VistaInstitucional, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Historial de cobranzas: todos los pagos (contado y recibos), confirmados y revertidos."""

    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'cobranzas.consultar'
    permisos_lectura = ('cobranzas.registrar', 'cobranzas.anular')
    modelo = Pago
    serializer_class = PagoSerializer
    lookup_field = 'referencia'
    lookup_value_regex = r'[Pp]-[A-Za-z0-9]+'

    def get_object(self):
        self.kwargs['referencia'] = normalizar_code(self.kwargs['referencia'])
        return super().get_object()

    def get_queryset(self):
        consulta = (self.consulta_base().select_related('cliente', 'forma_pago', 'usuario', 'recibo')
                    .prefetch_related(Prefetch('aplicaciones', queryset=AplicacionPago.objects.select_related(
                        'factura__punto').order_by('pk'))))
        if self.action != 'list':
            return consulta
        p = self.request.query_params
        for parametro, campo in (('estado', 'estado'), ('origen', 'origen')):
            if p.get(parametro):
                consulta = consulta.filter(**{campo: p[parametro]})
        if p.get('cliente'):
            consulta = consulta.filter(cliente__Code=normalizar_code(p['cliente']))
        if p.get('forma_pago'):
            consulta = consulta.filter(forma_pago__Code=normalizar_code(p['forma_pago']))
        if p.get('cobrador'):
            consulta = consulta.filter(usuario__nombre_usuario=p['cobrador'].strip().lower())
        if p.get('desde'):
            consulta = consulta.filter(fecha_hora__date__gte=p['desde'])
        if p.get('hasta'):
            consulta = consulta.filter(fecha_hora__date__lte=p['hasta'])
        return consulta.order_by('-fecha_hora')
