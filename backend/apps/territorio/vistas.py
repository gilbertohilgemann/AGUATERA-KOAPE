"""Zonas y barrios. No se borran: se archivan (activa/activo = false) y se pueden restaurar (auditado)."""
from django.db import IntegrityError, transaction

from comun.errores import ErrorNegocio
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.auditoria.servicios import registrar
from apps.identidad.permisos import RequierePermiso
from comun.codigos import VistaPorCode, normalizar_code
from comun.vistas import VistaInstitucional

from .models import Barrio, Zona
from .serializadores import BarrioSerializer, ZonaSerializer

LECTURA = ('padron.consultar', 'padron.conexiones', 'mapa.ver')


def _foto(objeto, campos):
    # La zona de un barrio se registra por su Code, nunca por el id interno.
    return {c: (objeto.zona.Code if c == 'zona_code' else getattr(objeto, c)) for c in campos}


class _BaseTerritorio(VistaPorCode, VistaInstitucional, mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                      mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'territorio.gestionar'
    permisos_lectura = LECTURA
    pagination_class = None
    entidad = ''
    campos_auditados = ()
    campo_activo = ''

    def get_serializer_context(self):
        return {**super().get_serializer_context(), 'institucion': self.institucion}

    def _guardar(self, serializador, **extra):
        # Dos altas simultáneas con el mismo código: la base lo frena; se responde 400, no 500.
        try:
            with transaction.atomic():
                return serializador.save(**extra)
        except IntegrityError:
            raise ErrorNegocio('Ya existe un registro con ese código.')

    def get_queryset(self):
        consulta = self.consulta_base()
        if self.request.query_params.get('activos') == '1':
            consulta = consulta.filter(**{self.campo_activo: True})
        return consulta

    def perform_create(self, serializador):
        with transaction.atomic():
            objeto = self._guardar(serializador, institucion=self.institucion)
            registrar(f'{self.entidad}_creado', request=self.request, entidad=self.entidad, entidad_id=objeto.Code,
                      despues=_foto(objeto, self.campos_auditados))

    def perform_update(self, serializador):
        antes = _foto(serializador.instance, self.campos_auditados)
        with transaction.atomic():
            objeto = self._guardar(serializador)
            despues = _foto(objeto, self.campos_auditados)
            accion = f'{self.entidad}_modificado'
            if antes[self.campo_activo] != despues[self.campo_activo]:
                accion = f'{self.entidad}_{"restaurado" if despues[self.campo_activo] else "archivado"}'
            registrar(accion, request=self.request, entidad=self.entidad, entidad_id=objeto.Code, antes=antes,
                      despues=despues, poligono_cambiado='poligono' in serializador.validated_data)


class ZonaVista(_BaseTerritorio):
    modelo = Zona
    serializer_class = ZonaSerializer
    entidad = 'zona'
    campo_activo = 'activa'
    campos_auditados = ('Code', 'nombre', 'color', 'activa')


class BarrioVista(_BaseTerritorio):
    modelo = Barrio
    serializer_class = BarrioSerializer
    entidad = 'barrio'
    campo_activo = 'activo'
    campos_auditados = ('Code', 'nombre', 'zona_code', 'activo')

    def get_queryset(self):
        consulta = super().get_queryset().select_related('zona')
        if self.request.query_params.get('zona'):
            consulta = consulta.filter(zona__Code=normalizar_code(self.request.query_params['zona']))
        return consulta
