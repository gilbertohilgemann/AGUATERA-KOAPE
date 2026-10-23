"""
API de recorridos.
- Oficina (`recorridos.gestionar`; lectura también con `lecturas.consultar`): armar, ordenar, asignar, estados.
- Cobrador (`lecturas.registrar`): sus recorridos abiertos, el paquete para trabajar sin conexión, iniciar y finalizar.
"""
from django.db.models import Prefetch
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.identidad.models import Usuario
from apps.identidad.permisos import RequierePermiso
from apps.padron.models import Conexion, InstalacionMedidor
from comun.codigos import VistaPorCode, normalizar_code
from comun.vistas import VistaInstitucional

from . import servicios
from .models import AsignacionRecorrido, Recorrido
from .serializadores import AgregarConexionesSerializer, CobradorSerializer, EstadoSerializer, RecorridoSerializer


class _Base(VistaPorCode, VistaInstitucional):
    permission_classes = [IsAuthenticated, RequierePermiso]
    modelo = Recorrido

    def get_serializer_context(self):
        return {**super().get_serializer_context(), 'institucion': self.institucion}

    def _validar(self, clase, instancia=None):
        s = clase(instancia, data=self.request.data, partial=instancia is not None, context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        return dict(s.validated_data)


def _paradas(recorrido):
    from apps.lecturas.models import Lectura
    vigentes = InstalacionMedidor.objects.filter(fecha_retiro__isnull=True).select_related('medidor')
    paradas = (recorrido.paradas.select_related('conexion__cliente', 'conexion__barrio')
               .prefetch_related(Prefetch('conexion__instalaciones', queryset=vigentes, to_attr='vigentes')))
    lecturas = {}
    for l in (Lectura.objects.filter(recorrido=recorrido).exclude(estado=Lectura.Estado.ANULADA)
              .order_by('capturada_en')):
        lecturas[l.conexion_id] = l
    return paradas, lecturas


class RecorridoVista(_Base, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permiso_requerido = 'recorridos.gestionar'
    permisos_lectura = ('lecturas.consultar',)
    serializer_class = RecorridoSerializer

    def get_queryset(self):
        consulta = self.consulta_base().prefetch_related(
            Prefetch('asignaciones', queryset=AsignacionRecorrido.objects.select_related('cobrador')))
        p = self.request.query_params
        if self.action == 'list':
            if p.get('periodo'):
                consulta = consulta.filter(periodo=p['periodo'])
            if p.get('estado'):
                consulta = consulta.filter(estado=p['estado'])
            elif p.get('incluir_anulados') != '1':
                consulta = consulta.exclude(estado=Recorrido.Estado.ANULADO)
        return consulta

    def _respuesta(self, recorrido, codigo=status.HTTP_200_OK):
        return Response(RecorridoSerializer(self.get_queryset().get(pk=recorrido.pk),
                                            context=self.get_serializer_context()).data, status=codigo)

    def create(self, request):
        recorrido = servicios.crear_recorrido(institucion=self.institucion, datos=self._validar(RecorridoSerializer),
                                              request=request)
        return self._respuesta(recorrido, status.HTTP_201_CREATED)

    def partial_update(self, request, **kwargs):
        recorrido = self.get_object()
        servicios.actualizar_recorrido(recorrido, self._validar(RecorridoSerializer, recorrido), request=request)
        return self._respuesta(recorrido)

    @action(detail=True, methods=['get'])
    def conexiones(self, request, **kwargs):
        recorrido = self.get_object()
        paradas, lecturas = _paradas(recorrido)
        filas = []
        for p in paradas:
            c, lectura = p.conexion, lecturas.get(p.conexion_id)
            filas.append({
                'orden': p.orden, 'conexion': c.Code, 'titular': c.cliente.nombre, 'direccion': c.direccion,
                'barrio': c.barrio.nombre if c.barrio else '', 'estado_conexion': c.get_estado_display(),
                'medidor': c.vigentes[0].medidor.Code if c.vigentes else None,
                'medidor_numero': c.vigentes[0].medidor.numero if c.vigentes else '',
                'lectura': {'comprobante': lectura.comprobante, 'estado': lectura.estado,
                            'estado_nombre': lectura.get_estado_display()} if lectura else None,
            })
        return Response(filas)

    @action(detail=True, methods=['post'], url_path='agregar-conexiones')
    def agregar_conexiones(self, request, **kwargs):
        recorrido = self.get_object()
        datos = self._validar(AgregarConexionesSerializer)
        resultado = servicios.agregar_conexiones(recorrido, zona=datos.get('zona'), barrio=datos.get('barrio'),
                                                 conexiones=datos.get('conexiones') or (), request=request)
        return Response(resultado)

    @action(detail=True, methods=['post'], url_path='quitar-conexion')
    def quitar_conexion(self, request, **kwargs):
        recorrido = self.get_object()
        conexion = Conexion.objects.de(self.institucion).filter(
            Code=normalizar_code(request.data.get('conexion'))).first()
        if conexion is None:
            raise NotFound('No existe esa conexión.')
        servicios.quitar_conexion(recorrido, conexion, request=request)
        return self._respuesta(recorrido)

    @action(detail=True, methods=['post'])
    def ordenar(self, request, **kwargs):
        recorrido = self.get_object()
        codes = request.data.get('conexiones')
        if not isinstance(codes, list):
            return Response({'detalle': 'Envíe la lista «conexiones» con los códigos en orden.'}, status=400)
        servicios.ordenar(recorrido, [normalizar_code(c) for c in codes], request=request)
        return self._respuesta(recorrido)

    def _cobrador(self):
        datos = self._validar(CobradorSerializer)
        usuario = Usuario.objects.de(self.institucion).filter(nombre_usuario=datos['usuario'].strip().lower()).first()
        if usuario is None:
            raise NotFound('No existe ese usuario en la institución.')
        return usuario

    @action(detail=True, methods=['post'], url_path='asignar-cobrador')
    def asignar_cobrador(self, request, **kwargs):
        recorrido = self.get_object()
        servicios.asignar_cobrador(recorrido, self._cobrador(), request=request)
        return self._respuesta(recorrido)

    @action(detail=True, methods=['post'], url_path='retirar-cobrador')
    def retirar_cobrador(self, request, **kwargs):
        recorrido = self.get_object()
        servicios.retirar_cobrador(recorrido, self._cobrador(), request=request)
        return self._respuesta(recorrido)

    @action(detail=True, methods=['post'])
    def estado(self, request, **kwargs):
        recorrido = self.get_object()
        datos = self._validar(EstadoSerializer)
        servicios.cambiar_estado(recorrido, datos['estado'], motivo=datos['motivo'], request=request)
        return self._respuesta(recorrido)

    @action(detail=False, methods=['get'])
    def cobradores(self, request):
        """Usuarios activos que pueden tomar lecturas (para asignarlos)."""
        candidatos = [u for u in Usuario.objects.de(self.institucion).filter(is_active=True).order_by('nombre_usuario')
                      if servicios.puede_leer(u)]
        return Response([{'usuario': u.nombre_usuario, 'nombre': u.get_full_name() or u.nombre_usuario}
                         for u in candidatos])


# --- Cobrador ------------------------------------------------------------------------------------------

class MisRecorridosVista(_Base, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Solo los recorridos abiertos asignados al usuario de la sesión: los demás responden 404."""

    permiso_requerido = 'lecturas.registrar'
    serializer_class = RecorridoSerializer
    pagination_class = None

    def get_queryset(self):
        return (self.consulta_base().filter(estado=Recorrido.Estado.ABIERTO, asignaciones__cobrador=self.request.user,
                                            asignaciones__activa=True)
                .prefetch_related(Prefetch('asignaciones', queryset=AsignacionRecorrido.objects.select_related('cobrador')))
                .distinct())

    def check_permissions(self, request):
        # Todo es lectura o acción propia del cobrador: siempre exige «lecturas.registrar» (también en GET).
        super().check_permissions(request)
        from apps.identidad.permisos import tiene_permiso
        from rest_framework.exceptions import PermissionDenied
        if not tiene_permiso(request, self.permiso_requerido):
            raise PermissionDenied('No tiene permiso para tomar lecturas.')

    @action(detail=True, methods=['get'])
    def paquete(self, request, **kwargs):
        """
        Todo lo necesario para trabajar sin conexión: las conexiones en orden, con titular, dirección, medidor y
        lectura anterior. El teléfono muestra los datos del titular recién después de la foto del medidor.
        """
        from apps.lecturas.servicios import lectura_anterior
        recorrido = self.get_object()
        paradas, lecturas = _paradas(recorrido)
        conexiones = []
        for p in paradas:
            c = p.conexion
            vigente = c.vigentes[0] if c.vigentes else None
            anterior = lectura_anterior(vigente, recorrido.periodo) if vigente else None
            lectura = lecturas.get(c.pk)
            conexiones.append({
                'orden': p.orden, 'conexion': c.Code, 'titular': c.cliente.nombre, 'direccion': c.direccion,
                'barrio': c.barrio.nombre if c.barrio else '',
                'lat': float(c.latitud) if c.latitud is not None else None,
                'lon': float(c.longitud) if c.longitud is not None else None,
                'tiene_foto_vivienda': bool(c.foto_vivienda),
                'medidor': vigente.medidor.Code if vigente else None,
                'medidor_numero': vigente.medidor.numero if vigente else '',
                'unidad': vigente.medidor.unidad if vigente else None,
                'lectura_maxima': str(vigente.medidor.lectura_maxima) if vigente and vigente.medidor.lectura_maxima else None,
                'lectura_anterior': str(anterior[0]) if anterior else None,
                'fecha_lectura_anterior': anterior[1].isoformat() if anterior else None,
                'leida': {'comprobante': lectura.comprobante, 'estado': lectura.estado} if lectura else None,
            })
        institucion = self.institucion
        return Response({
            'recorrido': RecorridoSerializer(recorrido, context=self.get_serializer_context()).data,
            'institucion': {'nombre': institucion.nombre, 'permite_galeria': institucion.lecturas_permite_galeria},
            'conexiones': conexiones,
        })

    @action(detail=True, methods=['get'], url_path=r'foto-vivienda/(?P<conexion>[A-Za-z0-9][A-Za-z0-9._-]*)')
    def foto_vivienda(self, request, conexion=None, **kwargs):
        """Foto de la vivienda, solo de una conexión de ESTE recorrido (el cobrador no tiene acceso al padrón)."""
        from comun import archivos_privados
        recorrido = self.get_object()
        parada = recorrido.paradas.select_related('conexion').filter(conexion__Code=normalizar_code(conexion)).first()
        if parada is None:
            raise NotFound('La conexión no está en el recorrido.')
        return archivos_privados.respuesta_archivo(self.institucion, parada.conexion.foto_vivienda)

    @action(detail=True, methods=['post'])
    def iniciar(self, request, **kwargs):
        servicios.iniciar(self.get_object(), request.user, request=request)
        return Response({'detalle': 'Recorrido iniciado.'})

    @action(detail=True, methods=['post'])
    def finalizar(self, request, **kwargs):
        servicios.finalizar(self.get_object(), request.user, request=request)
        return Response({'detalle': 'Recorrido finalizado.'})
