"""Panel de indicadores (inicio). Cada indicador trae su definición y solo se muestra a quien tiene el permiso."""
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

CERO = Decimal('0')


def _ind(titulo, valor, tipo='numero', definicion='', enlace='', alerta=False):
    return {'titulo': titulo, 'valor': str(valor), 'tipo': tipo, 'definicion': definicion, 'enlace': enlace,
            'alerta': bool(alerta)}


def panel(institucion, permisos: set) -> list[dict]:
    hoy = timezone.localdate()
    inicio_mes = hoy.replace(day=1)
    periodo = hoy.strftime('%Y-%m')
    secciones = []

    if 'padron.consultar' in permisos:
        from apps.padron.models import Conexion
        E = Conexion.Estado
        c = Conexion.objects.de(institucion).aggregate(
            total=Count('pk', filter=~Q(estado=E.ARCHIVADA)), activas=Count('pk', filter=Q(estado=E.ACTIVA)),
            suspendidas=Count('pk', filter=Q(estado=E.SUSPENDIDA)),
            sin_ubicacion=Count('pk', filter=~Q(estado=E.ARCHIVADA) & (Q(estado=E.PENDIENTE_UBICACION) | Q(latitud__isnull=True))))
        secciones.append({'titulo': 'Padrón', 'indicadores': [
            _ind('Conexiones', c['total'], definicion='Todas menos las archivadas.', enlace='conexiones'),
            _ind('Activas', c['activas'], enlace='conexiones'),
            _ind('Suspendidas', c['suspendidas'], enlace='conexiones'),
            _ind('Sin ubicación', c['sin_ubicacion'], definicion='Pendientes de ubicar o sin coordenadas.',
                 enlace='mapa', alerta=c['sin_ubicacion'] > 0)]})

    if 'lecturas.consultar' in permisos:
        from apps.lecturas.models import Lectura
        from apps.recorridos.models import ConexionRecorrido
        en_recorrido = ConexionRecorrido.objects.filter(institucion=institucion, periodo=periodo).count()
        lect = Lectura.objects.de(institucion).filter(periodo=periodo)
        leidas = lect.filter(estado=Lectura.Estado.CONFIRMADA).values('conexion').distinct().count()
        revision = (lect.filter(estado=Lectura.Estado.REVISION)
                    .exclude(conexion__in=lect.filter(estado=Lectura.Estado.CONFIRMADA).values('conexion'))
                    .values('conexion').distinct().count())
        consumo = lect.filter(estado=Lectura.Estado.CONFIRMADA).aggregate(s=Sum('consumo'))['s'] or CERO
        secciones.append({'titulo': f'Lecturas de {periodo}', 'indicadores': [
            _ind('Leídas', f'{leidas} de {en_recorrido}', 'texto', 'Conexiones con lectura confirmada / conexiones en '
                 'recorridos del mes.', 'lecturas'),
            _ind('En revisión', revision, definicion='Conexiones cuya lectura del mes espera revisión.', enlace='lecturas',
                 alerta=revision > 0),
            _ind('Consumo del mes', consumo, 'm3', 'Suma del consumo de las lecturas confirmadas.', 'informes')]})

    # Cada indicador exige el MISMO permiso que el informe que lo detalla.
    indicadores = []
    if 'facturacion.consultar' in permisos:
        from apps.facturacion.models import Factura
        facturado = (Factura.objects.de(institucion).filter(
            fecha_emision__gte=inicio_mes, estado__in=[Factura.Estado.EMITIDA, Factura.Estado.EN_TRAMITE])
            .aggregate(s=Sum('total'))['s'] or CERO)
        indicadores.append(_ind('Facturado', facturado, 'gs', 'Total de las facturas vigentes emitidas este mes (no es '
                                'dinero cobrado).', 'facturas'))
    if 'cobranzas.consultar' in permisos:
        from apps.cobranzas.models import Pago
        cobrado = (Pago.objects.de(institucion).filter(estado=Pago.Estado.CONFIRMADO).annotate(dia=TruncDate('fecha_hora'))
                   .filter(dia__gte=inicio_mes).aggregate(s=Sum('importe'))['s'] or CERO)
        indicadores.append(_ind('Cobrado', cobrado, 'gs', 'Pagos confirmados este mes (contado y recibos); sin los '
                                'revertidos.', 'cobros'))
    if 'facturacion.consultar' in permisos or 'cobranzas.consultar' in permisos:
        from apps.informes.consultas import Filtros, _facturas_con_saldo
        from apps.cobranzas.models import AplicacionPago
        from apps.facturacion.models import Factura
        # En la base, sin recorrer las facturas en Python: total de las que deben menos lo aplicado a ellas.
        ids = _facturas_con_saldo(institucion, Filtros(inicio_mes, hoy, periodo, periodo)).values('pk')
        vence = Q(fecha_vencimiento__lt=hoy)
        totales = Factura.objects.filter(pk__in=ids).aggregate(t=Sum('total'), v=Sum('total', filter=vence))
        pagos = AplicacionPago.objects.filter(factura__in=ids, estado='vigente').aggregate(
            t=Sum('importe'), v=Sum('importe', filter=Q(factura__fecha_vencimiento__lt=hoy)))
        saldo = (totales['t'] or CERO) - (pagos['t'] or CERO)
        vencido = (totales['v'] or CERO) - (pagos['v'] or CERO)
        indicadores += [
            _ind('Por cobrar (crédito)', saldo, 'gs', 'Saldo a hoy de todas las facturas a crédito.', 'informes'),
            _ind('Vencido', vencido, 'gs', 'Parte del saldo con el vencimiento ya pasado.', 'informes',
                 alerta=vencido > 0)]
    if indicadores:
        secciones.append({'titulo': 'Facturación y cobranzas del mes', 'indicadores': indicadores})

    if 'caja.supervisar' in permisos or 'gastos.consultar' in permisos:
        from apps.caja.models import Gasto, SesionCaja
        indicadores = []
        if 'caja.supervisar' in permisos:
            sesiones = SesionCaja.objects.de(institucion).aggregate(
                abiertas=Count('pk', filter=Q(estado='abierta')), revision=Count('pk', filter=Q(estado='en_revision')))
            indicadores += [_ind('Cajas abiertas', sesiones['abiertas'], enlace='sesiones-caja'),
                            _ind('Cajas con diferencias', sesiones['revision'], definicion='Cerradas con diferencias, '
                                 'pendientes de revisión.', enlace='sesiones-caja', alerta=sesiones['revision'] > 0)]
        if 'gastos.consultar' in permisos:
            g = Gasto.objects.de(institucion).filter(fecha__gte=inicio_mes).aggregate(
                total=Sum('importe', filter=Q(estado='confirmado')), pendientes=Count('pk', filter=Q(estado='registrado')))
            indicadores += [_ind('Gastos del mes', g['total'] or CERO, 'gs', 'Gastos confirmados con fecha de este mes.',
                                 'gastos'),
                            _ind('Gastos sin confirmar', g['pendientes'], enlace='gastos', alerta=g['pendientes'] > 0)]
        secciones.append({'titulo': 'Caja y gastos', 'indicadores': indicadores})

    if 'facturacion.consultar' in permisos and institucion.modalidad_facturacion == 'electronica':
        from apps.facturacion.models import SolicitudElectronica
        pendientes = SolicitudElectronica.objects.de(institucion).filter(
            estado__in=['pendiente', 'enviada', 'en_proceso', 'error_recuperable', 'desconocido']).count()
        secciones.append({'titulo': 'Factura electrónica', 'indicadores': [
            _ind('Sin respuesta final', pendientes, definicion='Solicitudes que todavía no fueron aprobadas ni '
                 'rechazadas por el proveedor.', enlace='facturas', alerta=pendientes > 0)]})
    return secciones
