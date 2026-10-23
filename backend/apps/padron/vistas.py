"""
API del padrón y del mapa.

Ninguna vista borra: clientes y conexiones se archivan; los medidores se dan de baja.
Lectura (GET) con `padron.consultar`; cada escritura pide su permiso específico.
"""
from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identidad.permisos import RequierePermiso, tiene_permiso
from apps.territorio.models import Barrio, Zona
from comun import archivos_privados
from comun.codigos import VistaPorCode, normalizar_code
from comun.vistas import VistaInstitucional

from . import servicios
from .models import Cliente, Conexion, InstalacionMedidor, Medidor
from .serializadores import (
    CambioEstadoSerializer, CambioTitularSerializer, ClienteSerializer, ConexionAltaSerializer,
    ConexionDetalleSerializer, ConexionEdicionSerializer, ConexionListaSerializer, InstalacionSerializer,
    InstalarSerializer, MedidorSerializer, RetirarSerializer, SustituirSerializer,
)

LECTURA = ('padron.consultar',)


class _Base(VistaPorCode, VistaInstitucional):
    permission_classes = [IsAuthenticated, RequierePermiso]

    def get_serializer_context(self):
        return {**super().get_serializer_context(), 'institucion': self.institucion}

    def _validar(self, clase, datos=None):
        serializador = clase(data=self.request.data if datos is None else datos,
                             context=self.get_serializer_context())
        serializador.is_valid(raise_exception=True)
        return serializador.validated_data


# --- Clientes ----------------------------------------------------------------------------------

class ClienteVista(_Base, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permiso_requerido = 'padron.clientes'
    permisos_lectura = LECTURA + ('padron.conexiones',)
    serializer_class = ClienteSerializer
    modelo = Cliente

    def get_queryset(self):
        consulta = self.consulta_base().annotate(
            cantidad_conexiones=Count('conexiones', filter=~Q(conexiones__estado=Conexion.Estado.ARCHIVADA)))
        if self.action != 'list':
            return consulta  # el detalle muestra también a los archivados (historial)
        p = self.request.query_params
        if p.get('buscar'):
            t = p['buscar'].strip()
            consulta = consulta.filter(Q(nombre__icontains=t) | Q(Code__icontains=t) | Q(documento__icontains=t)
                                       | Q(telefono__icontains=t))
        if p.get('estado'):
            consulta = consulta.filter(estado=p['estado'])
        elif p.get('incluir_archivados') != '1':
            consulta = consulta.exclude(estado=Cliente.Estado.ARCHIVADO)
        return consulta.order_by('nombre')

    def create(self, request):
        datos = self._validar(ClienteSerializer)
        cliente = servicios.crear_cliente(institucion=self.institucion, datos=dict(datos), request=request)
        return Response(ClienteSerializer(self.get_queryset().get(pk=cliente.pk)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, **kwargs):
        cliente = self.get_object()
        serializador = ClienteSerializer(cliente, data=request.data, partial=True, context=self.get_serializer_context())
        serializador.is_valid(raise_exception=True)
        datos = dict(serializador.validated_data)
        datos.pop('Code', None)
        servicios.actualizar_cliente(cliente, datos, request=request)
        return Response(ClienteSerializer(self.get_queryset().get(pk=cliente.pk)).data)

    @action(detail=True, methods=['get'])
    def conexiones(self, request, **kwargs):
        cliente = self.get_object()
        consulta = _consulta_conexiones(Conexion.objects.de(self.institucion).filter(cliente=cliente))
        return Response(ConexionListaSerializer(consulta, many=True).data)


# --- Medidores ---------------------------------------------------------------------------------

class MedidorVista(_Base, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permiso_requerido = 'padron.medidores'
    permisos_lectura = LECTURA + ('padron.conexiones',)
    serializer_class = MedidorSerializer
    modelo = Medidor

    def get_queryset(self):
        consulta = self.consulta_base().prefetch_related(
            Prefetch('instalaciones', queryset=InstalacionMedidor.objects.select_related('conexion')))
        p = self.request.query_params
        if p.get('buscar'):
            t = p['buscar'].strip()
            consulta = consulta.filter(Q(Code__icontains=t) | Q(numero__icontains=t) | Q(marca__icontains=t)
                                       | Q(modelo__icontains=t))
        if p.get('estado'):
            consulta = consulta.filter(estado=p['estado'])
        if p.get('instalables') == '1':
            consulta = consulta.filter(estado__in=[Medidor.Estado.DISPONIBLE, Medidor.Estado.RETIRADO])
        return consulta.order_by('Code')

    def create(self, request):
        datos = self._validar(MedidorSerializer)
        medidor = servicios.crear_medidor(institucion=self.institucion, datos=dict(datos), request=request)
        return Response(MedidorSerializer(self.get_queryset().get(pk=medidor.pk)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, **kwargs):
        medidor = self.get_object()
        serializador = MedidorSerializer(medidor, data=request.data, partial=True, context=self.get_serializer_context())
        serializador.is_valid(raise_exception=True)
        datos = dict(serializador.validated_data)
        datos.pop('Code', None)
        servicios.actualizar_medidor(medidor, datos, request=request)
        return Response(MedidorSerializer(self.get_queryset().get(pk=medidor.pk)).data)

    @action(detail=True, methods=['get'])
    def historial(self, request, **kwargs):
        medidor = self.get_object()
        consulta = medidor.instalaciones.select_related('conexion', 'medidor', 'instalado_por', 'retirado_por')
        return Response(InstalacionSerializer(consulta, many=True).data)


# --- Conexiones --------------------------------------------------------------------------------

def _consulta_conexiones(consulta):
    vigentes = InstalacionMedidor.objects.filter(fecha_retiro__isnull=True).select_related('medidor')
    return consulta.select_related('cliente', 'barrio__zona', 'tarifa').prefetch_related(
        Prefetch('instalaciones', queryset=vigentes, to_attr='instalaciones_vigentes'))


PERMISOS_DEUDA = ('cobranzas.consultar', 'facturacion.consultar')


def exigir_permiso_deuda(request) -> None:
    """Filtrar por deuda revela quién debe: exige poder consultar cobranzas o facturas."""
    from rest_framework.exceptions import PermissionDenied
    if request.query_params.get('deuda') and not any(tiene_permiso(request, p) for p in PERMISOS_DEUDA):
        raise PermissionDenied('Para filtrar por deuda necesita poder consultar cobranzas o facturas.')


def filtrar_conexiones(consulta, parametros):
    """
    Filtros combinables del padrón y del mapa (sección 8.2): texto, estado, zona, barrio, cliente, ubicación, con o
    sin lectura del período, recorrido, cobrador, sin medidor y estado de deuda (`deuda`: con · al_dia · morosa ·
    sin_facturar; definiciones en `cobranzas.servicios.condiciones_deuda_conexion`, D50).
    """
    p = parametros
    if p.get('buscar'):
        t = p['buscar'].strip()
        consulta = consulta.filter(Q(Code__icontains=t) | Q(direccion__icontains=t) | Q(cliente__nombre__icontains=t)
                                   | Q(cliente__Code__icontains=t) | Q(cliente__documento__icontains=t)
                                   | Q(instalaciones__medidor__Code__icontains=t, instalaciones__fecha_retiro__isnull=True)
                                   | Q(instalaciones__medidor__numero__icontains=t, instalaciones__fecha_retiro__isnull=True))
    estados = [e for e in (p.get('estado') or '').split(',') if e]
    if estados:
        consulta = consulta.filter(estado__in=estados)
    elif p.get('incluir_archivadas') != '1':
        consulta = consulta.exclude(estado=Conexion.Estado.ARCHIVADA)
    # Zona, barrio y cliente se filtran por su Code (nunca por el id interno).
    for parametro, campo in (('zona', 'barrio__zona__Code'), ('barrio', 'barrio__Code'), ('cliente', 'cliente__Code')):
        if p.get(parametro):
            consulta = consulta.filter(**{campo: normalizar_code(p[parametro])})
    if p.get('sin_barrio') == '1':
        consulta = consulta.filter(barrio__isnull=True)
    if p.get('ubicacion') == 'sin':
        consulta = consulta.filter(latitud__isnull=True)
    elif p.get('ubicacion') == 'con':
        consulta = consulta.filter(latitud__isnull=False)
    # Fase 3: con o sin lectura del período, por recorrido y por cobrador.
    if p.get('lectura') in ('con', 'sin') and p.get('periodo'):
        from apps.lecturas.models import Lectura
        leidas = Exists(Lectura.objects.filter(conexion=OuterRef('pk'), periodo=p['periodo'])
                        .exclude(estado=Lectura.Estado.ANULADA))
        consulta = consulta.filter(leidas) if p['lectura'] == 'con' else consulta.exclude(leidas)
    if p.get('recorrido'):
        consulta = consulta.filter(en_recorridos__recorrido__Code=normalizar_code(p['recorrido']))
    if p.get('cobrador'):
        from apps.recorridos.models import Recorrido
        consulta = consulta.filter(
            en_recorridos__recorrido__asignaciones__cobrador__nombre_usuario=p['cobrador'].strip().lower(),
            en_recorridos__recorrido__asignaciones__activa=True,
            en_recorridos__recorrido__estado__in=[Recorrido.Estado.PLANIFICADO, Recorrido.Estado.ABIERTO])
    if p.get('sin_medidor') == '1':
        consulta = consulta.exclude(Exists(InstalacionMedidor.objects.filter(conexion=OuterRef('pk'),
                                                                             fecha_retiro__isnull=True)))
    if p.get('deuda'):
        from apps.cobranzas.servicios import filtrar_por_deuda
        consulta = filtrar_por_deuda(consulta, p['deuda'])
    return consulta.distinct()


class ConexionVista(_Base, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permiso_requerido = 'padron.conexiones'
    permisos_lectura = LECTURA
    modelo = Conexion
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_serializer_class(self):
        return ConexionDetalleSerializer if self.action == 'retrieve' else ConexionListaSerializer

    def get_queryset(self):
        consulta = _consulta_conexiones(self.consulta_base())
        if self.action == 'retrieve':
            consulta = consulta.prefetch_related(
                Prefetch('instalaciones', queryset=InstalacionMedidor.objects.select_related(
                    'medidor', 'conexion', 'instalado_por', 'retirado_por')),
                'titularidades__cliente')
        elif self.action == 'list':
            exigir_permiso_deuda(self.request)
            consulta = filtrar_conexiones(consulta, self.request.query_params)
        return consulta.order_by('Code')

    def _detalle(self, conexion, codigo=status.HTTP_200_OK):
        self.action = 'retrieve'
        return Response(ConexionDetalleSerializer(self.get_queryset().get(pk=conexion.pk)).data, status=codigo)

    def create(self, request):
        datos = self._validar(ConexionAltaSerializer)
        conexion = servicios.crear_conexion(institucion=self.institucion, datos=dict(datos), usuario=request.user,
                                            request=request)
        return self._detalle(conexion, status.HTTP_201_CREATED)

    def partial_update(self, request, **kwargs):
        conexion = self.get_object()
        serializador = ConexionEdicionSerializer(conexion, data=request.data, partial=True,
                                                 context=self.get_serializer_context())
        serializador.is_valid(raise_exception=True)
        datos = dict(serializador.validated_data)
        datos.pop('Code', None)
        servicios.actualizar_conexion(conexion, datos, request=request)
        return self._detalle(conexion)

    @action(detail=True, methods=['post'])
    def estado(self, request, **kwargs):
        conexion = self.get_object()
        datos = self._validar(CambioEstadoSerializer)
        servicios.cambiar_estado_conexion(conexion, datos['estado'], motivo=datos['motivo'], request=request)
        return self._detalle(conexion)

    @action(detail=True, methods=['post'])
    def titular(self, request, **kwargs):
        conexion = self.get_object()
        datos = self._validar(CambioTitularSerializer)
        servicios.cambiar_titular(conexion, datos['cliente'], desde=datos['desde'], motivo=datos['motivo'],
                                  usuario=request.user, request=request)
        return self._detalle(conexion)

    @action(detail=True, methods=['get', 'post'], url_path='foto-vivienda')
    def foto_vivienda(self, request, **kwargs):
        conexion = self.get_object()
        if request.method == 'GET':
            return archivos_privados.respuesta_archivo(self.institucion, conexion.foto_vivienda)
        servicios.guardar_foto_vivienda(conexion, request.FILES.get('archivo'), request=request)
        return self._detalle(conexion)

    @action(detail=True, methods=['post'], url_path='instalar-medidor')
    def instalar_medidor(self, request, **kwargs):
        self._exigir_medidores(request)
        conexion = self.get_object()
        datos = self._validar(InstalarSerializer)
        servicios.instalar_medidor(conexion, datos['medidor'], fecha=datos['fecha'], lectura_inicial=datos['lectura_inicial'],
                                   usuario=request.user, observaciones=datos['observaciones'], request=request)
        return self._detalle(conexion)

    @action(detail=True, methods=['post'], url_path='retirar-medidor')
    def retirar_medidor(self, request, **kwargs):
        self._exigir_medidores(request)
        conexion = self.get_object()
        datos = self._validar(RetirarSerializer)
        servicios.retirar_medidor(conexion, fecha=datos['fecha'], lectura_retiro=datos['lectura_retiro'],
                                  motivo=datos['motivo'], usuario=request.user, estado_medidor=datos['estado_medidor'],
                                  aceptar_lectura_menor=datos['aceptar_lectura_menor'], request=request)
        return self._detalle(conexion)

    @action(detail=True, methods=['post'], url_path='sustituir-medidor')
    def sustituir_medidor(self, request, **kwargs):
        self._exigir_medidores(request)
        conexion = self.get_object()
        datos = self._validar(SustituirSerializer)
        servicios.sustituir_medidor(conexion, datos['medidor'], fecha=datos['fecha'], lectura_retiro=datos['lectura_retiro'],
                                    lectura_inicial=datos['lectura_inicial'], motivo=datos['motivo'], usuario=request.user,
                                    estado_medidor_retirado=datos['estado_medidor_retirado'],
                                    aceptar_lectura_menor=datos['aceptar_lectura_menor'], request=request)
        return self._detalle(conexion)

    def _exigir_medidores(self, request):
        from rest_framework.exceptions import PermissionDenied
        if not tiene_permiso(request, 'padron.medidores'):
            raise PermissionDenied('No tiene permiso para instalar o retirar medidores.')

    def check_permissions(self, request):
        # Instalar/retirar/sustituir piden «padron.medidores» (verificado en la acción), no «padron.conexiones».
        if self.action in ('instalar_medidor', 'retirar_medidor', 'sustituir_medidor'):
            self.permiso_requerido = 'padron.medidores'
        super().check_permissions(request)


# --- Mapa --------------------------------------------------------------------------------------

class MapaVista(APIView):
    """
    Todo lo que dibuja el mapa en una sola respuesta: zonas y barrios con sus polígonos y colores, y las
    conexiones con ubicación (más el conteo de las que no tienen). Mismos filtros que el padrón.
    En la Fase 3 el cobrador verá solo las conexiones de su recorrido.
    """

    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'mapa.ver'

    def get(self, request):
        from comun.vistas import institucion_de

        institucion = institucion_de(request)
        zonas = Zona.objects.de(institucion).order_by('nombre')
        barrios = Barrio.objects.de(institucion).select_related('zona').order_by('nombre')
        exigir_permiso_deuda(request)
        base = filtrar_conexiones(_consulta_conexiones(Conexion.objects.de(institucion)), request.query_params)
        con_ubicacion = base.filter(latitud__isnull=False)
        # Estado de deuda de cada punto (para colorear), solo para quien puede consultar cobranzas o facturas.
        ve_deuda = any(tiene_permiso(request, p) for p in PERMISOS_DEUDA)
        if ve_deuda:
            from apps.cobranzas.servicios import condiciones_deuda_conexion
            c = condiciones_deuda_conexion()
            con_ubicacion = con_ubicacion.annotate(d_vencida=c['vencida'], d_saldo=c['con_saldo'],
                                                   d_sin_facturar=c['sin_facturar'])
        conexiones = [{
            'Code': c.Code, 'lat': float(c.latitud), 'lon': float(c.longitud), 'estado': c.estado,
            'estado_nombre': c.get_estado_display(), 'titular': c.cliente.nombre, 'direccion': c.direccion,
            'barrio': c.barrio.nombre if c.barrio else '', 'zona': c.barrio.zona.Code if c.barrio else None,
            'medidor': c.instalaciones_vigentes[0].medidor.Code if c.instalaciones_vigentes else None,
            'tiene_foto': bool(c.foto_vivienda),
            **({'deuda': 'morosa' if c.d_vencida else 'con' if (c.d_saldo or c.d_sin_facturar) else 'al_dia'}
               if ve_deuda else {}),
        } for c in con_ubicacion[:5000]]
        return Response({
            'zonas': [{'Code': z.Code, 'nombre': z.nombre, 'color': z.color, 'poligono': z.poligono,
                       'activa': z.activa} for z in zonas],
            'barrios': [{'Code': b.Code, 'nombre': b.nombre, 'zona': b.zona.Code, 'color': b.zona.color,
                         'poligono': b.poligono, 'activo': b.activo} for b in barrios],
            'conexiones': conexiones,
            'sin_ubicacion': base.filter(latitud__isnull=True).count(),
            'total': base.count(),
        })


class ResumenPadronVista(APIView):
    """Números para el inicio del panel (definiciones explícitas: estados de la conexión, sin deuda todavía)."""

    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'padron.consultar'

    def get(self, request):
        from comun.vistas import institucion_de

        institucion = institucion_de(request)
        conexiones = Conexion.objects.de(institucion)
        por_estado = dict(conexiones.values_list('estado').annotate(n=Count('id')))
        return Response({
            'clientes': Cliente.objects.de(institucion).exclude(estado=Cliente.Estado.ARCHIVADO).count(),
            'conexiones': conexiones.exclude(estado=Conexion.Estado.ARCHIVADA).count(),
            'conexiones_por_estado': {e: por_estado.get(e, 0) for e in Conexion.Estado.values},
            'sin_ubicacion': conexiones.exclude(estado=Conexion.Estado.ARCHIVADA).filter(latitud__isnull=True).count(),
            'sin_medidor': conexiones.exclude(estado=Conexion.Estado.ARCHIVADA).exclude(Exists(
                InstalacionMedidor.objects.filter(conexion=OuterRef('pk'), fecha_retiro__isnull=True))).count(),
            'medidores_disponibles': Medidor.objects.de(institucion).filter(estado=Medidor.Estado.DISPONIBLE).count(),
        })

