"""API de informes: catálogo, datos con filtros, exportación y panel. Cada informe exige su propio permiso."""
from decimal import Decimal

from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditoria.servicios import registrar
from apps.identidad.permisos import permisos_efectivos
from comun.errores import ErrorNegocio
from comun.vistas import institucion_de

from . import consultas, exportar
from .panel import panel


def _json(v):
    return str(v) if isinstance(v, Decimal) else v


def _informe(request, codigo):
    informe = consultas.POR_CODIGO.get(codigo)
    if informe is None:
        raise NotFound('No existe ese informe.')
    if not any(p in permisos_efectivos(request.user) for p in informe.permisos):
        raise PermissionDenied('No tiene permiso para este informe.')
    return informe


class _Base(APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(request.user, 'debe_cambiar_contrasena', False):
            raise PermissionDenied('Debe cambiar su contraseña antes de continuar.')


class CatalogoInformesVista(_Base):
    def get(self, request):
        institucion_de(request)
        return Response([{'codigo': i.codigo, 'titulo': i.titulo, 'grupo': i.grupo, 'definicion': i.definicion,
                          'filtros': list(i.filtros), 'agrupaciones': [{'valor': v, 'texto': t} for v, t in i.agrupaciones]}
                         for i in consultas.disponibles(permisos_efectivos(request.user))])


class InformeVista(_Base):
    def get(self, request, codigo):
        institucion = institucion_de(request)
        informe = _informe(request, codigo)
        filtros = consultas.leer_filtros(request.query_params)
        datos = informe.funcion(institucion, filtros)
        formato = request.query_params.get('formato', '')
        if formato in ('xlsx', 'csv'):
            texto = ' · '.join(f'{k}: {v}' for k, v in vars(filtros).items() if v and (k in informe.filtros or k == 'agrupar'))
            registrar('informe_exportado', request=request, entidad='informe', entidad_id=informe.codigo,
                      formato=formato, filtros=texto, filas=len(datos['filas']))
            return (exportar.a_excel(informe, datos, institucion, texto) if formato == 'xlsx'
                    else exportar.a_csv(informe, datos))
        if formato:
            raise ErrorNegocio('Formato inválido: use xlsx o csv.')
        return Response({
            'codigo': informe.codigo, 'titulo': informe.titulo, 'definicion': informe.definicion,
            'columnas': datos['columnas'],
            'filas': [{k: _json(v) for k, v in fila.items()} for fila in datos['filas']],
            'totales': {k: _json(v) for k, v in (datos.get('totales') or {}).items()} or None,
            'filtros': {k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in vars(filtros).items()},
        })


class PanelVista(_Base):
    def get(self, request):
        return Response(panel(institucion_de(request), permisos_efectivos(request.user)))
