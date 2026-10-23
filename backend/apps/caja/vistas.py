"""API de caja y gastos (Fase 7). Las reglas están en `servicios.py`."""
from django.db.models import Prefetch, Q
from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditoria.servicios import registrar
from apps.identidad.permisos import RequierePermiso, tiene_permiso
from comun import archivos_privados
from comun.codigos import VistaPorCode, normalizar_code
from comun.errores import ErrorNegocio
from comun.vistas import VistaInstitucional, institucion_de

from . import servicios
from .models import AdjuntoGasto, Caja, CategoriaGasto, Gasto, MovimientoCaja, SesionCaja
from .pdf import pdf_boleta, pdf_sesion
from .serializadores import (CajaSerializer, CategoriaGastoSerializer, GastoSerializer, MovimientoSerializer,
                             SesionSerializer, adjunto_por_codigo)


def _pdf(contenido: bytes, nombre: str) -> HttpResponse:
    respuesta = HttpResponse(contenido, content_type='application/pdf')
    respuesta['Content-Disposition'] = f'inline; filename="{nombre}"'
    respuesta['Cache-Control'] = 'private, no-store'
    return respuesta


class _Maestro(VistaPorCode, VistaInstitucional, mixins.ListModelMixin, mixins.RetrieveModelMixin,
               viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, RequierePermiso]
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
        objeto = s.save(institucion=self.institucion)
        registrar(f'{self.entidad}_creada', request=request, entidad=self.entidad, entidad_id=objeto.Code,
                  despues=s.data)
        return Response(self.get_serializer(objeto).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, **kwargs):
        objeto = self.get_object()
        antes = self.get_serializer(objeto).data
        s = self.get_serializer(objeto, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        registrar(f'{self.entidad}_modificada', request=request, entidad=self.entidad, entidad_id=objeto.Code,
                  antes=antes, despues=s.data)
        return Response(s.data)


class CajaVista(_Maestro):
    permiso_requerido = 'caja.supervisar'
    permisos_lectura = ('caja.operar',)
    modelo = Caja
    serializer_class = CajaSerializer
    entidad = 'caja'


class CategoriaGastoVista(_Maestro):
    permiso_requerido = 'gastos.confirmar'
    permisos_lectura = ('gastos.registrar', 'gastos.consultar')
    modelo = CategoriaGasto
    serializer_class = CategoriaGastoSerializer
    entidad = 'categoria_gasto'


class MiCajaVista(APIView):
    """GET: la sesión abierta de quien consulta (o null) y las cajas libres. POST: abrir {caja, saldo_inicial}."""

    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'caja.operar'

    def get(self, request):
        institucion = institucion_de(request)
        sesion = servicios.sesion_abierta_de(request.user)
        ocupadas = SesionCaja.objects.filter(institucion=institucion, estado='abierta').values('caja_id')
        cajas = Caja.objects.de(institucion).filter(activa=True).exclude(pk__in=ocupadas)
        return Response({'sesion': SesionSerializer(sesion).data if sesion else None,
                         'cajas_libres': [{'Code': c.Code, 'nombre': c.nombre} for c in cajas]})

    def post(self, request):
        institucion = institucion_de(request)
        caja = Caja.objects.de(institucion).filter(Code=normalizar_code(request.data.get('caja'))).first()
        if caja is None:
            raise ErrorNegocio('Elija la caja.')
        sesion = servicios.abrir_sesion(institucion=institucion, caja=caja, usuario=request.user,
                                        saldo_inicial=request.data.get('saldo_inicial', 0), request=request)
        return Response({'sesion': SesionSerializer(sesion).data, 'cajas_libres': []}, status=status.HTTP_201_CREATED)


class SesionCajaVista(VistaInstitucional, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Sesiones de caja. Quien solo opera ve las suyas; el supervisor ve todas y revisa las diferencias."""

    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'caja.operar'
    permisos_lectura = ('caja.supervisar',)
    modelo = SesionCaja
    serializer_class = SesionSerializer
    lookup_field = 'referencia'
    lookup_value_regex = r'[Ss]-[A-Za-z0-9]+'

    def check_permissions(self, request):
        if getattr(self, 'action', None) == 'revisar':
            self.permiso_requerido = 'caja.supervisar'
        super().check_permissions(request)

    def get_object(self):
        self.kwargs['referencia'] = normalizar_code(self.kwargs['referencia'])
        return super().get_object()

    def get_queryset(self):
        consulta = self.consulta_base().select_related('caja', 'responsable', 'revisada_por')
        if not tiene_permiso(self.request, 'caja.supervisar'):
            consulta = consulta.filter(responsable=self.request.user)
        if self.action != 'list':
            return consulta
        p = self.request.query_params
        if p.get('estado'):
            consulta = consulta.filter(estado=p['estado'])
        if p.get('caja'):
            consulta = consulta.filter(caja__Code=normalizar_code(p['caja']))
        if p.get('responsable'):
            consulta = consulta.filter(responsable__nombre_usuario=p['responsable'].strip().lower())
        if p.get('desde'):
            consulta = consulta.filter(abierta_en__date__gte=p['desde'])
        if p.get('hasta'):
            consulta = consulta.filter(abierta_en__date__lte=p['hasta'])
        return consulta.order_by('-abierta_en')

    def _respuesta(self, sesion):
        return Response(SesionSerializer(SesionCaja.objects.get(pk=sesion.pk)).data)

    @action(detail=True, methods=['get'])
    def movimientos(self, request, **kwargs):
        sesion = self.get_object()
        movimientos = (sesion.movimientos.select_related('forma_pago', 'usuario', 'pago__recibo', 'gasto', 'reversion')
                       .order_by('fecha_hora', 'pk'))
        return Response(MovimientoSerializer(movimientos, many=True).data)

    @action(detail=True, methods=['post'])
    def cerrar(self, request, **kwargs):
        sesion = self.get_object()
        lista = request.data.get('declarados') or []
        if not isinstance(lista, list) or not all(isinstance(d, dict) and isinstance(d.get('forma_pago'), str)
                                                  for d in lista):
            raise ErrorNegocio('Formato inválido: declarados = [{forma_pago, importe}].')
        codigos = [normalizar_code(d['forma_pago']) for d in lista]
        if len(set(codigos)) != len(codigos):
            raise ErrorNegocio('Una forma de pago figura dos veces.')
        declarados = dict(zip(codigos, (d.get('importe') for d in lista)))
        servicios.cerrar_sesion(sesion, declarados=declarados, observaciones=request.data.get('observaciones', ''),
                                usuario=request.user, puede_supervisar=tiene_permiso(request, 'caja.supervisar'),
                                request=request)
        return self._respuesta(sesion)

    @action(detail=True, methods=['post'])
    def revisar(self, request, **kwargs):
        sesion = self.get_object()
        servicios.revisar_sesion(sesion, comentario=request.data.get('comentario', ''), usuario=request.user,
                                 request=request)
        return self._respuesta(sesion)

    @action(detail=True, methods=['get'])
    def pdf(self, request, **kwargs):
        sesion = self.get_object()
        return _pdf(pdf_sesion(sesion), f'caja-{sesion.referencia}.pdf')


class GastoVista(VistaInstitucional, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'gastos.registrar'
    permisos_lectura = ('gastos.consultar', 'gastos.confirmar')
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    modelo = Gasto
    serializer_class = GastoSerializer
    lookup_field = 'referencia'
    lookup_value_regex = r'[Gg]-[A-Za-z0-9]+'

    def check_permissions(self, request):
        if getattr(self, 'action', None) in ('confirmar', 'anular'):
            self.permiso_requerido = 'gastos.confirmar'
        super().check_permissions(request)

    def get_object(self):
        self.kwargs['referencia'] = normalizar_code(self.kwargs['referencia'])
        return super().get_object()

    def get_serializer_context(self):
        return {**super().get_serializer_context(), 'institucion': self.institucion}

    def get_queryset(self):
        consulta = (self.consulta_base().select_related(
            'categoria', 'forma_pago', 'sesion', 'registrado_por', 'confirmado_por', 'anulado_por', 'boleta')
            .prefetch_related(Prefetch('adjuntos', queryset=AdjuntoGasto.objects.select_related('subido_por'))))
        if self.action != 'list':
            return consulta
        p = self.request.query_params
        if p.get('estado'):
            consulta = consulta.filter(estado=p['estado'])
        if p.get('categoria'):
            consulta = consulta.filter(categoria__Code=normalizar_code(p['categoria']))
        if p.get('sesion'):
            consulta = consulta.filter(sesion__referencia=normalizar_code(p['sesion']))
        if p.get('desde'):
            consulta = consulta.filter(fecha__gte=p['desde'])
        if p.get('hasta'):
            consulta = consulta.filter(fecha__lte=p['hasta'])
        if p.get('buscar'):
            t = p['buscar'].strip()
            consulta = consulta.filter(Q(motivo__icontains=t) | Q(beneficiario__icontains=t) |
                                       Q(numero_comprobante__icontains=t) | Q(referencia__iexact=t))
        return consulta.order_by('-fecha', '-creado_en')

    def _respuesta(self, gasto, codigo=status.HTTP_200_OK):
        self.action = 'retrieve'
        return Response(GastoSerializer(self.get_queryset().get(pk=gasto.pk)).data, status=codigo)

    def _validar(self, instancia=None):
        s = GastoSerializer(instancia, data=self.request.data, partial=instancia is not None,
                            context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        return dict(s.validated_data)

    def create(self, request):
        gasto = servicios.registrar_gasto(institucion=self.institucion, datos=self._validar(), usuario=request.user,
                                          request=request)
        return self._respuesta(gasto, status.HTTP_201_CREATED)

    def partial_update(self, request, **kwargs):
        gasto = self.get_object()
        servicios.editar_gasto(gasto, self._validar(gasto), usuario=request.user, request=request)
        return self._respuesta(gasto)

    @action(detail=True, methods=['post'])
    def confirmar(self, request, **kwargs):
        gasto = self.get_object()
        servicios.confirmar_gasto(gasto, usuario=request.user, request=request)
        return self._respuesta(gasto)

    @action(detail=True, methods=['post'])
    def anular(self, request, **kwargs):
        gasto = self.get_object()
        servicios.anular_gasto(gasto, motivo=request.data.get('motivo', ''), usuario=request.user, request=request)
        return self._respuesta(gasto)

    @action(detail=True, methods=['post'])
    def adjuntos(self, request, **kwargs):
        gasto = self.get_object()
        servicios.adjuntar(gasto, request.FILES.get('archivo'), tipo=request.data.get('tipo', 'comprobante'),
                           usuario=request.user, request=request)
        return self._respuesta(gasto, status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path=r'adjuntos/(?P<codigo>[0-9a-f]{32})')
    def adjunto(self, request, codigo=None, **kwargs):
        adjunto = adjunto_por_codigo(self.get_object(), codigo)
        if adjunto is None:
            raise NotFound('No existe ese adjunto.')
        return archivos_privados.respuesta_archivo(self.institucion, adjunto.archivo)

    @action(detail=True, methods=['post'])
    def boleta(self, request, **kwargs):
        gasto = self.get_object()
        servicios.generar_boleta(gasto, usuario=request.user, request=request)
        return self._respuesta(gasto)

    @action(detail=True, methods=['get'], url_path='boleta/pdf')
    def boleta_pdf(self, request, **kwargs):
        gasto = self.get_object()
        boleta = getattr(gasto, 'boleta', None)
        if boleta is None:
            raise NotFound('El gasto no tiene boleta interna.')
        return _pdf(pdf_boleta(boleta), f'boleta-{boleta.numero_impreso}.pdf')
