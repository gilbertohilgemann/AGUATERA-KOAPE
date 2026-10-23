"""
API de lecturas.
- Cobrador (`lecturas.registrar`): enviar lecturas (idempotente por `id_operacion`), ver las propias y su comprobante.
- Oficina (`lecturas.consultar`; las acciones con `lecturas.revisar`): consultar, ver fotos, comprobante,
  autorizar excepciones, corregir y anular.
"""
from django.db.models import Q
from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.identidad.permisos import RequierePermiso, tiene_permiso
from comun import archivos_privados
from comun.codigos import normalizar_code
from comun.vistas import VistaInstitucional

from . import servicios
from .comprobante import generar_pdf
from .ticket import generar_ticket
from .models import Lectura
from .serializadores import (AutorizarSerializer, CorregirSerializer, LecturaSerializer, MotivoSerializer,
                             RegistroLecturaSerializer)


class _Base(VistaInstitucional):
    permission_classes = [IsAuthenticated, RequierePermiso]
    modelo = Lectura
    serializer_class = LecturaSerializer
    lookup_field = 'comprobante'
    lookup_url_kwarg = 'comprobante'
    lookup_value_regex = r'[Ll]-[A-Za-z0-9]+'

    def get_object(self):
        self.kwargs['comprobante'] = normalizar_code(self.kwargs['comprobante'])
        return super().get_object()

    def consulta_lecturas(self):
        return (self.consulta_base().select_related('conexion__cliente', 'medidor', 'recorrido', 'cobrador',
                                                    'resuelta_por', 'institucion')
                .prefetch_related('fotos'))

    def _ticket(self, lectura):
        """Ticket para impresora térmica: `?ancho=58` (por defecto) u `80` mm."""
        ancho = 80 if self.request.query_params.get('ancho') == '80' else 58
        respuesta = HttpResponse(generar_ticket(lectura, ancho), content_type='application/pdf')
        respuesta['Content-Disposition'] = f'inline; filename="ticket-{lectura.comprobante}.pdf"'
        respuesta['Cache-Control'] = 'private, no-store'
        return respuesta

    def _pdf(self, lectura):
        respuesta = HttpResponse(generar_pdf(lectura), content_type='application/pdf')
        respuesta['Content-Disposition'] = f'inline; filename="lectura-{lectura.comprobante}.pdf"'
        respuesta['Cache-Control'] = 'private, no-store'
        return respuesta

    def _foto(self, lectura, n):
        fotos = list(lectura.fotos.all())
        try:
            foto = fotos[int(n)]
        except (ValueError, IndexError):
            raise NotFound('No existe esa foto.')
        return archivos_privados.respuesta_archivo(self.institucion, foto.archivo)


def _deudas(lectura) -> dict:
    """Paso 6: deudas de la conexión, recién DESPUÉS de registrar la lectura (nunca antes)."""
    if lectura.motivo_revision == Lectura.MotivoRevision.FUERA_DEL_RECORRIDO:
        return {'disponible': False, 'pendientes_de_facturar': [], 'facturas': [], 'mensaje': ''}
    from apps.facturacion.facturas import deudas_de_conexion
    return deudas_de_conexion(lectura.conexion)


def _para_cobrador(lectura) -> dict:
    """Si la conexión ya no está en su recorrido, el cobrador no ve los datos del titular (queda para la oficina)."""
    datos = LecturaSerializer(lectura).data
    if lectura.motivo_revision == Lectura.MotivoRevision.FUERA_DEL_RECORRIDO:
        datos.update(titular='', direccion='', conexion='')
    return datos


class LecturaCobradorVista(_Base, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """El cobrador solo ve sus propias lecturas."""

    permiso_requerido = 'lecturas.registrar'
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def check_permissions(self, request):
        super().check_permissions(request)
        if not tiene_permiso(request, self.permiso_requerido):
            raise PermissionDenied('No tiene permiso para tomar lecturas.')

    def get_queryset(self):
        return self.consulta_lecturas().filter(cobrador=self.request.user)

    def create(self, request):
        datos = RegistroLecturaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        lectura, creada = servicios.registrar_lectura(
            institucion=self.institucion, usuario=request.user, datos=dict(datos.validated_data),
            foto=request.FILES.get('foto'), fotos_adicionales=request.FILES.getlist('adicionales'), request=request)
        lectura = self.get_queryset().get(pk=lectura.pk)
        cuerpo = {**_para_cobrador(lectura), 'ya_recibida': not creada, 'deudas': _deudas(lectura)}
        return Response(cuerpo, status=status.HTTP_201_CREATED if creada else status.HTTP_200_OK)

    def retrieve(self, request, **kwargs):
        lectura = self.get_object()
        return Response({**_para_cobrador(lectura), 'deudas': _deudas(lectura)})

    @action(detail=True, methods=['get'], url_path='comprobante')
    def comprobante_pdf(self, request, **kwargs):
        return self._pdf(self.get_object())

    @action(detail=True, methods=['get'], url_path='ticket')
    def ticket(self, request, **kwargs):
        return self._ticket(self.get_object())


class LecturaVista(_Base, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permiso_requerido = 'lecturas.revisar'
    permisos_lectura = ('lecturas.consultar',)

    def get_queryset(self):
        consulta = self.consulta_lecturas()
        if self.action != 'list':
            return consulta
        p = self.request.query_params
        if p.get('periodo'):
            consulta = consulta.filter(periodo=p['periodo'])
        if p.get('estado'):
            consulta = consulta.filter(estado=p['estado'])
        for parametro, campo in (('recorrido', 'recorrido__Code'), ('conexion', 'conexion__Code'),
                                 ('medidor', 'medidor__Code'), ('zona', 'conexion__barrio__zona__Code')):
            if p.get(parametro):
                consulta = consulta.filter(**{campo: normalizar_code(p[parametro])})
        if p.get('cobrador'):
            consulta = consulta.filter(cobrador__nombre_usuario=p['cobrador'].strip().lower())
        if p.get('buscar'):
            t = p['buscar'].strip()
            consulta = consulta.filter(Q(comprobante__icontains=t) | Q(conexion__Code__icontains=t)
                                       | Q(conexion__cliente__nombre__icontains=t) | Q(medidor__Code__icontains=t)
                                       | Q(medidor__numero__icontains=t))
        return consulta.order_by('-capturada_en')

    @action(detail=True, methods=['get'], url_path=r'fotos/(?P<n>\d+)')
    def foto(self, request, n=None, **kwargs):
        return self._foto(self.get_object(), n)

    @action(detail=True, methods=['get'], url_path='comprobante')
    def comprobante_pdf(self, request, **kwargs):
        return self._pdf(self.get_object())

    @action(detail=True, methods=['get'], url_path='ticket')
    def ticket(self, request, **kwargs):
        return self._ticket(self.get_object())

    def _accion(self, clase, funcion, **extra):
        lectura = self.get_object()
        datos = clase(data=self.request.data)
        datos.is_valid(raise_exception=True)
        funcion(lectura, usuario=self.request.user, request=self.request, **dict(datos.validated_data), **extra)
        return Response(LecturaSerializer(self.consulta_lecturas().get(pk=lectura.pk)).data)

    @action(detail=True, methods=['post'])
    def autorizar(self, request, **kwargs):
        return self._accion(AutorizarSerializer, servicios.autorizar)

    @action(detail=True, methods=['post'])
    def corregir(self, request, **kwargs):
        return self._accion(CorregirSerializer, servicios.corregir)

    @action(detail=True, methods=['post'])
    def anular(self, request, **kwargs):
        return self._accion(MotivoSerializer, servicios.anular)
