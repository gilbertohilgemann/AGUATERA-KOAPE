"""
API del portal de abonados (`/api/v1/portal/…`). Solo lectura de lo PROPIO: cada consulta se limita a las fichas de
cliente con el documento de la cuenta, en instituciones que ofrecen el portal. Las rutas de una institución usan su
código público (el mismo con el que ingresa el personal), nunca ids internos.
"""
from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.cobranzas.models import Pago, Recibo
from apps.cobranzas.servicios import con_saldo, estado_cobro
from apps.facturacion.facturas import pendientes_de_facturar
from apps.facturacion.models import Factura
from apps.lecturas.models import FotoLectura, Lectura
from apps.padron.models import Conexion, TitularidadConexion
from apps.plataforma.models import Institucion
from comun import archivos_privados
from comun.codigos import normalizar_code

from . import servicios
from .autenticacion import AutenticacionPortal

class EsAbonado(BasePermission):
    message = 'Ingrese al portal para consultar su cuenta.'

    def has_permission(self, request, view):
        return getattr(request.auth, 'cuenta_id', None) is not None


def _gs(v):
    return f'{v:.2f}' if v is not None else None


class _Publica(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [ScopedRateThrottle]


class SolicitarPinVista(_Publica):
    throttle_scope = 'portal_pin'

    def post(self, request):
        servicios.solicitar_pin(documento=request.data.get('documento', ''), correo=request.data.get('correo', ''),
                                request=request)
        return Response({'detalle': servicios.MENSAJE_ENVIO})


class IngresarVista(_Publica):
    throttle_scope = 'ingreso'

    def post(self, request):
        cuenta, token = servicios.ingresar(usuario=request.data.get('usuario', ''), clave=request.data.get('clave', ''),
                                           request=request)
        return Response({'token': token, 'debe_cambiar_clave': cuenta.debe_cambiar_clave, 'nombre': cuenta.nombre})


class _Privada(APIView):
    authentication_classes = [AutenticacionPortal]
    permission_classes = [EsAbonado]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # Con el PIN solo se puede elegir la contraseña.
        if request.user.debe_cambiar_clave and not getattr(self, 'permitir_sin_clave', False):
            raise PermissionDenied('Primero elija su contraseña.')

    def clientes(self, codigo=None):
        institucion = None
        if codigo is not None:
            institucion = Institucion.objects.filter(codigo=normalizar_code(codigo)).first()
            if institucion is None:
                raise NotFound('No tiene cuenta en esa institución.')
        clientes = list(servicios.clientes_de_cuenta(self.request.user, institucion=institucion))
        if codigo is not None and not clientes:
            raise NotFound('No tiene cuenta en esa institución.')
        return institucion, clientes


class YoVista(_Privada):
    permitir_sin_clave = True

    def get(self, request):
        c = request.user
        return Response({'nombre': c.nombre, 'correo': c.correo, 'documento': c.documento,
                         'debe_cambiar_clave': c.debe_cambiar_clave})


class CambiarClaveVista(_Privada):
    permitir_sin_clave = True
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'contrasena'

    def post(self, request):
        servicios.cambiar_clave(request.user, nueva=request.data.get('nueva', ''), actual=request.data.get('actual', ''),
                                sesion=request.auth, request=request)
        return Response({'detalle': 'Contraseña guardada.'})


class SalirVista(_Privada):
    permitir_sin_clave = True

    def post(self, request):
        servicios.salir(request.auth)
        return Response({'detalle': 'Sesión cerrada.'})


def _deuda(institucion, clientes):
    from decimal import Decimal
    # Solo los consumos de cuando la persona era la titular (no los del titular anterior, aunque sigan sin facturar).
    pendientes = list(pendientes_de_facturar(institucion).filter(lectura__in=_lecturas_propias(institucion, clientes)))
    from apps.cobranzas.servicios import facturas_con_saldo
    facturas = [f for c in clientes for f in facturas_con_saldo(institucion, c)]
    hoy = timezone.localdate()
    saldo = sum((f.saldo for f in facturas), Decimal('0'))
    vencido = sum((f.saldo for f in facturas if f.fecha_vencimiento and f.fecha_vencimiento < hoy), Decimal('0'))
    a_facturar = sum((q.total for q in pendientes), Decimal('0'))
    return pendientes, facturas, saldo, vencido, a_facturar


class ResumenVista(_Privada):
    """Todas las instituciones donde la persona es cliente, con su deuda en cada una."""

    def get(self, request):
        por_institucion = {}
        for c in servicios.clientes_de_cuenta(request.user):
            por_institucion.setdefault(c.institucion_id, (c.institucion, []))[1].append(c)
        salida = []
        for institucion, clientes in por_institucion.values():
            _, facturas, saldo, vencido, a_facturar = _deuda(institucion, clientes)
            salida.append({
                'institucion': {'codigo': institucion.codigo, 'nombre': institucion.nombre,
                                'telefono': institucion.telefono, 'direccion': institucion.direccion},
                'clientes': [{'Code': c.Code, 'nombre': c.nombre} for c in clientes],
                'conexiones': Conexion.objects.filter(cliente__in=clientes).exclude(estado='archivada').count(),
                'saldo_facturas': _gs(saldo), 'vencido': _gs(vencido), 'a_facturar': _gs(a_facturar),
                'deuda_total': _gs(saldo + a_facturar)})
        return Response(sorted(salida, key=lambda x: x['institucion']['nombre']))


class ConexionesVista(_Privada):
    def get(self, request, codigo):
        institucion, clientes = self.clientes(codigo)
        from apps.tarifas.servicios import tarifa_de
        filas = []
        for cx in (Conexion.objects.filter(cliente__in=clientes).exclude(estado='archivada')
                   .select_related('barrio__zona', 'tarifa').order_by('Code')):
            instalacion = cx.instalaciones.filter(fecha_retiro__isnull=True).select_related('medidor').first()
            ultima = (_lecturas_propias(institucion, clientes).filter(conexion=cx)
                      .order_by('-periodo', '-capturada_en').first())
            tarifa = tarifa_de(cx)
            filas.append({'Code': cx.Code, 'direccion': cx.direccion, 'barrio': cx.barrio.nombre if cx.barrio else '',
                          'estado': cx.get_estado_display(), 'medidor': instalacion.medidor.Code if instalacion else None,
                          'medidor_numero': instalacion.medidor.numero if instalacion else '',
                          'tarifa': tarifa.nombre if tarifa else '',
                          'ultima_lectura': {'periodo': ultima.periodo, 'lectura': str(ultima.lectura_actual),
                                             'consumo': str(ultima.consumo)} if ultima else None})
        return Response(filas)


class DeudaVista(_Privada):
    def get(self, request, codigo):
        institucion, clientes = self.clientes(codigo)
        pendientes, facturas, saldo, vencido, a_facturar = _deuda(institucion, clientes)
        return Response({
            'saldo_facturas': _gs(saldo), 'vencido': _gs(vencido), 'a_facturar': _gs(a_facturar),
            'deuda_total': _gs(saldo + a_facturar),
            'pendientes_de_facturar': [{'periodo': q.periodo, 'conexion': q.conexion.Code, 'consumo': str(q.consumo),
                                        'total': _gs(q.total)} for q in pendientes],
            'facturas': [{'referencia': f.referencia, 'numero': f.numero_impreso, 'fecha_emision': f.fecha_emision,
                          'fecha_vencimiento': f.fecha_vencimiento, 'total': _gs(f.total), 'saldo': _gs(f.saldo),
                          'estado_cobro': estado_cobro(f, f.saldo)} for f in facturas]})


class FacturasVista(_Privada):
    def get(self, request, codigo):
        institucion, clientes = self.clientes(codigo)
        facturas = (con_saldo(Factura.objects.filter(institucion=institucion, cliente__in=clientes)
                              .exclude(estado=Factura.Estado.RECHAZADA)).select_related('punto')
                    .order_by('-fecha_emision', '-SerNr')[:60])
        return Response([{'referencia': f.referencia, 'numero': f.numero_impreso, 'fecha_emision': f.fecha_emision,
                          'condicion': f.get_condicion_display(), 'fecha_vencimiento': f.fecha_vencimiento,
                          'total': _gs(f.total), 'saldo': _gs(f.saldo if f.estado == 'emitida' else 0),
                          'estado': f.get_estado_display(), 'anulada': f.estado == 'anulada',
                          'estado_cobro': estado_cobro(f, f.saldo), 'pdf': f.modalidad == 'autoimpresa'}
                         for f in facturas])


class PagosVista(_Privada):
    def get(self, request, codigo):
        institucion, clientes = self.clientes(codigo)
        pagos = (Pago.objects.filter(institucion=institucion, cliente__in=clientes)
                 .select_related('forma_pago', 'recibo').prefetch_related('aplicaciones__factura__punto')
                 .order_by('-fecha_hora')[:60])
        return Response([{'fecha_hora': p.fecha_hora, 'importe': _gs(p.importe), 'forma_pago': p.forma_pago.nombre,
                          'origen': p.get_origen_display(), 'estado': p.get_estado_display(),
                          'revertido': p.estado == 'revertido',
                          'recibo': p.recibo.numero_impreso if hasattr(p, 'recibo') else None,
                          'facturas': [a.factura.numero_impreso for a in p.aplicaciones.all()]} for p in pagos])


def _lecturas_propias(institucion, clientes):
    """Lecturas de las conexiones mientras la persona era la titular (no las del titular anterior)."""
    filtro = Q(pk__in=[])
    for t in TitularidadConexion.objects.filter(cliente__in=clientes):
        rango = Q(conexion_id=t.conexion_id, capturada_en__date__gte=t.desde)
        if t.hasta:
            # `hasta` es el día en que empieza el titular siguiente: ese día ya es del nuevo.
            rango &= Q(capturada_en__date__lt=t.hasta)
        filtro |= rango
    return Lectura.objects.filter(filtro, institucion=institucion, estado=Lectura.Estado.CONFIRMADA)


class LecturasVista(_Privada):
    def get(self, request, codigo):
        institucion, clientes = self.clientes(codigo)
        lecturas = (_lecturas_propias(institucion, clientes).select_related('conexion', 'medidor')
                    .order_by('-periodo', 'conexion__Code')[:120])
        con_foto = set(FotoLectura.objects.filter(lectura__in=lecturas, principal=True).values_list('lectura_id', flat=True))
        return Response([{'comprobante': l.comprobante, 'periodo': l.periodo, 'conexion': l.conexion.Code,
                          'medidor': l.medidor.Code, 'medidor_numero': l.medidor.numero, 'lectura_anterior': str(l.lectura_anterior),
                          'lectura_actual': str(l.lectura_actual), 'consumo': str(l.consumo),
                          'fecha': l.capturada_en, 'foto': l.pk in con_foto} for l in lecturas])


class FotoLecturaVista(_Privada):
    def get(self, request, codigo, comprobante):
        institucion, clientes = self.clientes(codigo)
        lectura = _lecturas_propias(institucion, clientes).filter(comprobante=normalizar_code(comprobante)).first()
        foto = FotoLectura.objects.filter(lectura=lectura, principal=True).first() if lectura else None
        if foto is None:
            raise Http404('No existe esa foto.')
        return archivos_privados.respuesta_archivo(institucion, foto.archivo)


class FacturaPdfVista(_Privada):
    def get(self, request, codigo, referencia):
        from apps.facturacion.pdf import generar_pdf
        institucion, clientes = self.clientes(codigo)
        factura = Factura.objects.filter(institucion=institucion, cliente__in=clientes, modalidad='autoimpresa',
                                         referencia=normalizar_code(referencia)).first()
        if factura is None:
            raise Http404('No existe esa factura.')
        return _pdf(generar_pdf(factura), f'factura-{factura.numero_impreso}.pdf')


class ReciboPdfVista(_Privada):
    def get(self, request, codigo, numero):
        from apps.cobranzas.pdf import generar_pdf_recibo
        institucion, clientes = self.clientes(codigo)
        recibo = Recibo.objects.filter(institucion=institucion, cliente__in=clientes, numero=int(numero)).first()
        if recibo is None:
            raise Http404('No existe ese recibo.')
        return _pdf(generar_pdf_recibo(recibo), f'recibo-{recibo.numero_impreso}.pdf')


def _pdf(contenido, nombre):
    from django.http import HttpResponse
    respuesta = HttpResponse(contenido, content_type='application/pdf')
    respuesta['Content-Disposition'] = f'inline; filename="{nombre}"'
    respuesta['Cache-Control'] = 'private, no-store'
    return respuesta
