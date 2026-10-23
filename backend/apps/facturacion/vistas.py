"""API de puntos de expedición y rangos de numeración (configuración de la institución). No se borra nada."""
import re

from django.db.models import Prefetch, Q
from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cobranzas.models import FormaPago
from apps.cobranzas.servicios import con_saldo
from apps.identidad.permisos import RequierePermiso
from apps.padron.models import Cliente
from comun.codigos import VistaPorCode, normalizar_code
from comun.vistas import VistaInstitucional

from . import facturas, servicios
from .models import Factura, PuntoExpedicion, RangoNumeracion
from .pdf import generar_pdf
from .serializadores import EmitirSerializer, FacturaSerializer, PendienteSerializer, PuntoSerializer, RangoSerializer

PERMISO = 'facturacion.numeracion'
LECTURA = ('institucion.ver',)


class _Base(VistaPorCode, VistaInstitucional, mixins.ListModelMixin, mixins.RetrieveModelMixin,
            viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = PERMISO
    permisos_lectura = LECTURA
    pagination_class = None

    def get_serializer_context(self):
        return {**super().get_serializer_context(), 'institucion': self.institucion}

    def _validar(self, instancia=None):
        serializador = self.get_serializer_class()(instancia, data=self.request.data, partial=instancia is not None,
                                                   context=self.get_serializer_context())
        serializador.is_valid(raise_exception=True)
        return dict(serializador.validated_data)

    def _respuesta(self, objeto, codigo=status.HTTP_200_OK):
        return Response(self.get_serializer_class()(self.get_queryset().get(pk=objeto.pk),
                                                    context=self.get_serializer_context()).data, status=codigo)


class PuntoExpedicionVista(_Base):
    modelo = PuntoExpedicion
    serializer_class = PuntoSerializer

    def get_queryset(self):
        consulta = self.consulta_base().prefetch_related(
            Prefetch('rangos', queryset=RangoNumeracion.objects.select_related('punto')))
        if self.action == 'list' and self.request.query_params.get('activos') == '1':
            consulta = consulta.filter(activo=True)
        return consulta

    def create(self, request):
        punto = servicios.crear_punto(institucion=self.institucion, datos=self._validar(), request=request)
        return self._respuesta(punto, status.HTTP_201_CREATED)

    def partial_update(self, request, **kwargs):
        punto = self.get_object()
        servicios.actualizar_punto(punto, self._validar(punto), request=request)
        return self._respuesta(punto)


class RangoNumeracionVista(_Base):
    modelo = RangoNumeracion
    serializer_class = RangoSerializer

    def get_queryset(self):
        consulta = self.consulta_base().select_related('punto')
        p = self.request.query_params
        if self.action == 'list':
            if p.get('punto'):
                consulta = consulta.filter(punto__Code=normalizar_code(p['punto']))
            if p.get('tipo'):
                consulta = consulta.filter(tipo_documento=p['tipo'])
        return consulta

    def create(self, request):
        rango = servicios.crear_rango(institucion=self.institucion, datos=self._validar(), request=request)
        return self._respuesta(rango, status.HTTP_201_CREATED)

    def partial_update(self, request, **kwargs):
        rango = self.get_object()
        servicios.actualizar_rango(rango, self._validar(rango), request=request)
        return self._respuesta(rango)


# --- Facturas (Fase 5) ----------------------------------------------------------------------------------

class FacturaVista(VistaInstitucional, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Facturas: se buscan por su referencia (F-XXXXXXXX). Emitir con `facturacion.emitir`, anular con
    `facturacion.anular`, consultar con `facturacion.consultar`."""

    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'facturacion.emitir'
    permisos_lectura = ('facturacion.consultar', 'facturacion.anular')
    modelo = Factura
    serializer_class = FacturaSerializer
    lookup_field = 'referencia'
    lookup_value_regex = r'[Ff]-[A-Za-z0-9]+'

    def get_object(self):
        self.kwargs['referencia'] = normalizar_code(self.kwargs['referencia'])
        return super().get_object()

    def get_serializer_context(self):
        return {**super().get_serializer_context(), 'institucion': self.institucion}

    def check_permissions(self, request):
        if getattr(self, 'action', None) == 'anular':
            self.permiso_requerido = 'facturacion.anular'
        super().check_permissions(request)

    def get_queryset(self):
        consulta = (self.consulta_base().select_related('punto', 'cliente', 'emitida_por', 'anulada_por',
                                                        'solicitud__proveedor')
                    .prefetch_related('lineas__liquidacion', 'asignaciones__liquidacion__conexion',
                                      'aplicaciones_pago__pago__forma_pago', 'aplicaciones_pago__pago__recibo',
                                      'aplicaciones_pago__pago__usuario'))
        consulta = con_saldo(consulta)
        if self.action != 'list':
            return consulta
        p = self.request.query_params
        if p.get('estado'):
            consulta = consulta.filter(estado=p['estado'])
        if p.get('condicion'):
            consulta = consulta.filter(condicion=p['condicion'])
        if p.get('con_saldo') == '1':
            consulta = consulta.filter(estado=Factura.Estado.EMITIDA, saldo__gt=0)
        if p.get('cliente'):
            consulta = consulta.filter(cliente__Code=normalizar_code(p['cliente']))
        if p.get('desde'):
            consulta = consulta.filter(fecha_emision__gte=p['desde'])
        if p.get('hasta'):
            consulta = consulta.filter(fecha_emision__lte=p['hasta'])
        if p.get('buscar'):
            t = p['buscar'].strip()
            filtro = Q(referencia__icontains=t) | Q(cliente_nombre__icontains=t) | Q(cliente_documento__icontains=t)
            numero = re.fullmatch(r'(?:(\d{1,3})-(\d{1,3})-)?(\d{1,7})', t)
            if numero:
                por_numero = Q(SerNr=int(numero.group(3)))
                if numero.group(1):
                    por_numero &= Q(punto__establecimiento=numero.group(1).zfill(3), punto__punto=numero.group(2).zfill(3))
                filtro |= por_numero
            consulta = consulta.filter(filtro)
        return consulta.order_by('-fecha_emision', '-creado_en')

    def _respuesta(self, factura, codigo=status.HTTP_200_OK):
        self.action = 'retrieve'
        return Response(FacturaSerializer(self.get_queryset().get(pk=factura.pk)).data, status=codigo)

    def create(self, request):
        datos = EmitirSerializer(data=request.data, context=self.get_serializer_context())
        datos.is_valid(raise_exception=True)
        d = datos.validated_data
        factura = facturas.emitir(institucion=self.institucion, cliente=d['cliente'], liquidaciones=d['liquidaciones'],
                                  condicion=d['condicion'], punto=d.get('punto'), observaciones=d['observaciones'],
                                  usuario=request.user, forma_pago=d.get('forma_pago'),
                                  referencia_externa=d['referencia_externa'], request=request)
        return self._respuesta(factura, status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def pdf(self, request, **kwargs):
        factura = self.get_object()
        if factura.modalidad != Factura.Modalidad.AUTOIMPRESA:
            raise NotFound('La representación de una factura electrónica la entrega el proveedor.')
        respuesta = HttpResponse(generar_pdf(factura), content_type='application/pdf')
        respuesta['Content-Disposition'] = f'inline; filename="factura-{factura.numero_impreso}.pdf"'
        respuesta['Cache-Control'] = 'private, no-store'
        return respuesta

    @action(detail=True, methods=['post'])
    def anular(self, request, **kwargs):
        factura = self.get_object()
        facturas.anular(factura, motivo=request.data.get('motivo', ''), usuario=request.user, request=request)
        return self._respuesta(factura)

    @action(detail=True, methods=['post'], url_path='consultar-estado')
    def consultar_estado(self, request, **kwargs):
        factura = self.get_object()
        facturas.consultar_electronica(factura, request=request)
        return self._respuesta(factura)

    @action(detail=True, methods=['post'])
    def reintentar(self, request, **kwargs):
        factura = self.get_object()
        facturas.enviar_electronica(factura, request=request)
        return self._respuesta(factura)


class PendientesFacturarVista(APIView):
    """Lo que el cliente puede pagar: sus liquidaciones vigentes sin facturar (de todas sus conexiones)."""

    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'facturacion.emitir'
    permisos_lectura = ('facturacion.consultar',)

    def get(self, request):
        from comun.vistas import institucion_de
        institucion = institucion_de(request)
        cliente = Cliente.objects.de(institucion).filter(Code=normalizar_code(request.query_params.get('cliente'))).first()
        if cliente is None:
            raise NotFound('No existe ese cliente.')
        pendientes = facturas.pendientes_de_facturar(institucion, cliente=cliente)
        modalidad = institucion.modalidad_facturacion
        puntos = PuntoExpedicion.objects.de(institucion).filter(activo=True)
        return Response({
            'cliente': {'Code': cliente.Code, 'nombre': cliente.nombre, 'documento': cliente.documento,
                        'direccion': cliente.direccion_referencia},
            'pendientes': PendienteSerializer(pendientes, many=True).data,
            'modalidad': modalidad, 'dias_vencimiento_credito': institucion.dias_vencimiento_credito,
            'puntos': [{'Code': p.Code, 'prefijo': p.prefijo, 'nombre': p.nombre} for p in puntos],
            'formas_pago': [{'Code': f.Code, 'nombre': f.nombre, 'requiere_referencia': f.requiere_referencia}
                            for f in FormaPago.objects.de(institucion).filter(activa=True)],
        })
