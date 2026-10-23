"""
Informes (sección 15). Cada informe declara su DEFINICIÓN (qué cuenta y qué no), sus columnas y los permisos que lo
habilitan; los datos salen siempre de la institución de la sesión. Se separa lo FACTURADO (lo que se emitió) de lo
COBRADO (dinero efectivamente recibido).

Todos devuelven `{'columnas': [...], 'filas': [...], 'totales': {...} | None}`; la misma estructura alimenta la
pantalla, la exportación a Excel y a CSV.
"""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Exists, F, Max, Min, OuterRef, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone

from comun.codigos import normalizar_code
from comun.errores import ErrorNegocio

CERO = Decimal('0')


@dataclass
class Filtros:
    desde: date
    hasta: date
    periodo_desde: str
    periodo_hasta: str
    zona: str = ''
    barrio: str = ''
    cobrador: str = ''
    estado: str = ''
    agrupar: str = ''


def _fecha(valor, defecto: date) -> date:
    if not valor:
        return defecto
    try:
        return date.fromisoformat(str(valor))
    except ValueError:
        raise ErrorNegocio(f'Fecha inválida: {valor} (use AAAA-MM-DD).')


def _periodo(valor, defecto: str) -> str:
    if not valor:
        return defecto
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', str(valor)):
        raise ErrorNegocio(f'Período inválido: {valor} (use AAAA-MM).')
    return str(valor)


ESTADOS_SESION = ('', 'abierta', 'en_revision', 'cerrada')


def leer_filtros(parametros) -> Filtros:
    """Por defecto: el mes en curso (fechas) y los últimos 12 períodos."""
    for clave, valor in parametros.items():
        if '\x00' in str(valor) or len(str(valor)) > 100:
            raise ErrorNegocio(f'Valor inválido en el filtro «{clave}».')
    if (parametros.get('estado') or '').strip() not in ESTADOS_SESION:
        raise ErrorNegocio('Estado inválido.')
    hoy = timezone.localdate()
    inicio_mes = hoy.replace(day=1)
    desde = _fecha(parametros.get('desde'), inicio_mes)
    hasta = _fecha(parametros.get('hasta'), hoy)
    if hasta < desde:
        raise ErrorNegocio('La fecha «hasta» es anterior a «desde».')
    if (hasta - desde).days > 3700:
        raise ErrorNegocio('El rango de fechas es demasiado largo (máximo 10 años).')
    hace_un_anio = (inicio_mes - timedelta(days=330)).strftime('%Y-%m')
    return Filtros(
        desde=desde, hasta=hasta, periodo_desde=_periodo(parametros.get('periodo_desde'), hace_un_anio),
        periodo_hasta=_periodo(parametros.get('periodo_hasta'), hoy.strftime('%Y-%m')),
        zona=normalizar_code(parametros.get('zona')), barrio=normalizar_code(parametros.get('barrio')),
        cobrador=(parametros.get('cobrador') or '').strip().lower(), estado=(parametros.get('estado') or '').strip(),
        agrupar=(parametros.get('agrupar') or '').strip())


def _territorio(consulta, f: Filtros, prefijo='barrio'):
    """Filtro por zona / barrio a través del barrio de la conexión (`prefijo` = ruta hasta el barrio)."""
    if f.zona:
        consulta = consulta.filter(**{f'{prefijo}__zona__Code': f.zona})
    if f.barrio:
        consulta = consulta.filter(**{f'{prefijo}__Code': f.barrio})
    return consulta


def _rango(consulta, campo, f: Filtros):
    return consulta.filter(**{f'{campo}__gte': f.desde, f'{campo}__lte': f.hasta})


def _col(clave, titulo, tipo='texto'):
    return {'clave': clave, 'titulo': titulo, 'tipo': tipo}


def _sumar(filas, claves):
    return {c: sum((Decimal(str(fila.get(c) or 0)) for fila in filas), CERO) for c in claves}


def _zona_barrio(fila, base='barrio'):
    return {'zona': fila.get(f'{base}__zona__nombre') or 'Sin zona', 'barrio': fila.get(f'{base}__nombre') or 'Sin barrio'}


# --- Padrón y lecturas ----------------------------------------------------------------------------------

def conexiones(institucion, f: Filtros):
    from apps.padron.models import Conexion
    E = Conexion.Estado
    consulta = _territorio(Conexion.objects.de(institucion), f)
    filas = []
    datos = (consulta.values('barrio__zona__nombre', 'barrio__nombre')
             .annotate(total=Count('pk', filter=~Q(estado=E.ARCHIVADA)),
                       activas=Count('pk', filter=Q(estado=E.ACTIVA)),
                       suspendidas=Count('pk', filter=Q(estado=E.SUSPENDIDA)),
                       desconectadas=Count('pk', filter=Q(estado=E.DESCONECTADA)),
                       en_instalacion=Count('pk', filter=Q(estado=E.EN_INSTALACION)),
                       pendiente_ubicacion=Count('pk', filter=Q(estado=E.PENDIENTE_UBICACION) |
                                                 (Q(latitud__isnull=True) & ~Q(estado=E.ARCHIVADA))),
                       archivadas=Count('pk', filter=Q(estado=E.ARCHIVADA)))
             .order_by('barrio__zona__nombre', 'barrio__nombre'))
    for d in datos:
        filas.append({**_zona_barrio(d), **{k: d[k] for k in ('total', 'activas', 'suspendidas', 'desconectadas',
                                                             'en_instalacion', 'pendiente_ubicacion', 'archivadas')}})
    numeros = ['total', 'activas', 'suspendidas', 'desconectadas', 'en_instalacion', 'pendiente_ubicacion', 'archivadas']
    return {'columnas': [_col('zona', 'Zona'), _col('barrio', 'Barrio'), _col('total', 'Total (sin archivadas)', 'numero'),
                         _col('activas', 'Activas', 'numero'), _col('suspendidas', 'Suspendidas', 'numero'),
                         _col('desconectadas', 'Desconectadas', 'numero'), _col('en_instalacion', 'En instalación', 'numero'),
                         _col('pendiente_ubicacion', 'Sin ubicación', 'numero'), _col('archivadas', 'Archivadas', 'numero')],
            'filas': filas, 'totales': _sumar(filas, numeros)}


def lecturas(institucion, f: Filtros):
    from apps.lecturas.models import Lectura
    from apps.recorridos.models import ConexionRecorrido, Recorrido
    recorridos = Recorrido.objects.de(institucion).filter(periodo__gte=f.periodo_desde, periodo__lte=f.periodo_hasta)
    if f.cobrador:
        recorridos = recorridos.filter(asignaciones__cobrador__nombre_usuario=f.cobrador, asignaciones__activa=True)
    filas = []
    for r in recorridos.distinct().order_by('-periodo', 'Code'):
        paradas = _territorio(ConexionRecorrido.objects.filter(recorrido=r), f, 'conexion__barrio')
        lecturas_r = _territorio(Lectura.objects.filter(recorrido=r), f, 'conexion__barrio')
        total = paradas.count()
        # Solo las conexiones que siguen en el recorrido (si se quitó una ya leída, no suma: el avance no pasa del 100 %).
        lecturas_r = lecturas_r.filter(conexion__in=paradas.values('conexion'))
        leidas = lecturas_r.filter(estado=Lectura.Estado.CONFIRMADA).values('conexion').distinct().count()
        revision = (lecturas_r.filter(estado=Lectura.Estado.REVISION)
                    .exclude(conexion__in=lecturas_r.filter(estado=Lectura.Estado.CONFIRMADA).values('conexion'))
                    .values('conexion').distinct().count())
        filas.append({'periodo': r.periodo, 'recorrido': f'{r.Code} · {r.nombre}', 'estado': r.get_estado_display(),
                      'conexiones': total, 'leidas': leidas, 'en_revision': revision,
                      'pendientes': max(total - leidas - revision, 0),
                      'avance': round(Decimal(leidas * 100) / total, 1) if total else CERO})
    return {'columnas': [_col('periodo', 'Período'), _col('recorrido', 'Recorrido'), _col('estado', 'Estado'),
                         _col('conexiones', 'Conexiones', 'numero'), _col('leidas', 'Leídas', 'numero'),
                         _col('en_revision', 'En revisión', 'numero'), _col('pendientes', 'Pendientes', 'numero'),
                         _col('avance', 'Avance %', 'porcentaje')],
            'filas': filas, 'totales': _sumar(filas, ['conexiones', 'leidas', 'en_revision', 'pendientes'])}


def consumo(institucion, f: Filtros):
    from apps.lecturas.models import Lectura
    consulta = _territorio(Lectura.objects.de(institucion).filter(
        estado=Lectura.Estado.CONFIRMADA, periodo__gte=f.periodo_desde, periodo__lte=f.periodo_hasta), f,
        'conexion__barrio')
    filas = []
    for d in (consulta.values('periodo', 'conexion__barrio__zona__nombre', 'conexion__barrio__nombre')
              .annotate(lecturas=Count('pk'), consumo=Sum('consumo'))
              .order_by('-periodo', 'conexion__barrio__zona__nombre', 'conexion__barrio__nombre')):
        total = d['consumo'] or CERO
        filas.append({'periodo': d['periodo'], **_zona_barrio(d, 'conexion__barrio'), 'lecturas': d['lecturas'],
                      'consumo': total, 'promedio': (total / d['lecturas']).quantize(Decimal('0.01')) if d['lecturas'] else CERO})
    return {'columnas': [_col('periodo', 'Período'), _col('zona', 'Zona'), _col('barrio', 'Barrio'),
                         _col('lecturas', 'Lecturas', 'numero'), _col('consumo', 'Consumo m³', 'decimal'),
                         _col('promedio', 'Promedio m³ por lectura', 'decimal')],
            'filas': filas, 'totales': _sumar(filas, ['lecturas', 'consumo'])}


# --- Liquidaciones, facturas, saldos ------------------------------------------------------------------

def liquidaciones(institucion, f: Filtros):
    from apps.tarifas.models import Liquidacion
    consulta = _territorio(Liquidacion.objects.de(institucion).filter(
        estado=Liquidacion.Estado.VIGENTE, periodo__gte=f.periodo_desde, periodo__lte=f.periodo_hasta), f,
        'conexion__barrio')
    filas = []
    for d in (consulta.values('periodo').annotate(
            cantidad=Count('pk'), consumo=Sum('consumo'), exento=Sum('subtotal_exento'), g5=Sum('subtotal_iva5'),
            g10=Sum('subtotal_iva10'), iva5=Sum('iva5'), iva10=Sum('iva10'), total=Sum('total')).order_by('-periodo')):
        filas.append({'periodo': d['periodo'], 'cantidad': d['cantidad'], 'consumo': d['consumo'] or CERO,
                      'gravado': (d['g5'] or CERO) + (d['g10'] or CERO), 'iva': (d['iva5'] or CERO) + (d['iva10'] or CERO),
                      'exento': d['exento'] or CERO, 'total': d['total'] or CERO})
    return {'columnas': [_col('periodo', 'Período'), _col('cantidad', 'Liquidaciones', 'numero'),
                         _col('consumo', 'Consumo m³', 'decimal'), _col('gravado', 'Gravado (sin IVA)', 'gs'),
                         _col('iva', 'IVA', 'gs'), _col('exento', 'Exento', 'gs'), _col('total', 'Total', 'gs')],
            'filas': filas, 'totales': _sumar(filas, ['cantidad', 'consumo', 'gravado', 'iva', 'exento', 'total'])}


def facturas(institucion, f: Filtros):
    from apps.facturacion.models import Factura
    base = _rango(Factura.objects.de(institucion), 'fecha_emision', f)
    vigentes = Q(estado__in=[Factura.Estado.EMITIDA, Factura.Estado.EN_TRAMITE])
    # fecha_emision ya es una fecha: por día se agrupa directo (TruncDate es para fecha y hora).
    truncar = TruncMonth('fecha_emision') if f.agrupar == 'mes' else F('fecha_emision')
    filas = []
    for d in (base.annotate(dia=truncar).values('dia').annotate(
            emitidas=Count('pk', filter=vigentes),
            contado=Sum('total', filter=vigentes & Q(condicion='contado')),
            credito=Sum('total', filter=vigentes & Q(condicion='credito')),
            total=Sum('total', filter=vigentes), anuladas=Count('pk', filter=Q(estado=Factura.Estado.ANULADA)))
            .order_by('-dia')):
        fecha_dia = d['dia'].date() if hasattr(d['dia'], 'date') else d['dia']
        filas.append({'fecha': fecha_dia.strftime('%Y-%m') if f.agrupar == 'mes' else fecha_dia.isoformat(),
                      'emitidas': d['emitidas'], 'contado': d['contado'] or CERO, 'credito': d['credito'] or CERO,
                      'total': d['total'] or CERO, 'anuladas': d['anuladas']})
    return {'columnas': [_col('fecha', 'Mes' if f.agrupar == 'mes' else 'Fecha', 'texto' if f.agrupar == 'mes' else 'fecha'),
                         _col('emitidas', 'Facturas vigentes', 'numero'), _col('contado', 'Contado', 'gs'),
                         _col('credito', 'Crédito', 'gs'), _col('total', 'Total facturado', 'gs'),
                         _col('anuladas', 'Anuladas', 'numero')],
            'filas': filas, 'totales': _sumar(filas, ['emitidas', 'contado', 'credito', 'total', 'anuladas'])}


def _facturas_con_saldo(institucion, f: Filtros):
    from apps.cobranzas.servicios import con_saldo
    from apps.facturacion.models import Factura
    # También las que están en trámite con el proveedor electrónico: ya no figuran como «sin facturar».
    consulta = con_saldo(Factura.objects.de(institucion).filter(
        condicion=Factura.Condicion.CREDITO, estado__in=[Factura.Estado.EMITIDA, Factura.Estado.EN_TRAMITE])
    ).filter(saldo__gt=0)
    if f.zona or f.barrio:
        from apps.padron.models import Conexion
        en_zona = _territorio(Conexion.objects.de(institucion), f).values('cliente')
        consulta = consulta.filter(cliente__in=en_zona)
    return consulta.select_related('cliente')


def saldos_clientes(institucion, f: Filtros):
    from apps.facturacion.facturas import pendientes_de_facturar
    hoy = timezone.localdate()
    clientes = {}
    for fac in _facturas_con_saldo(institucion, f):
        c = clientes.setdefault(fac.cliente_id, {'cliente': fac.cliente.Code, 'nombre': fac.cliente.nombre,
                                                 'facturas': 0, 'saldo': CERO, 'vencido': CERO, 'dias_atraso': 0,
                                                 'a_facturar': CERO})
        c['facturas'] += 1
        c['saldo'] += fac.saldo
        if fac.fecha_vencimiento and fac.fecha_vencimiento < hoy:
            c['vencido'] += fac.saldo
            c['dias_atraso'] = max(c['dias_atraso'], (hoy - fac.fecha_vencimiento).days)
    pendientes = pendientes_de_facturar(institucion)
    if f.zona or f.barrio:
        pendientes = _territorio(pendientes, f, 'conexion__barrio')
    for q in pendientes:
        cliente = q.conexion.cliente
        c = clientes.setdefault(cliente.pk, {'cliente': cliente.Code, 'nombre': cliente.nombre, 'facturas': 0,
                                             'saldo': CERO, 'vencido': CERO, 'dias_atraso': 0, 'a_facturar': CERO})
        c['a_facturar'] += q.total
    filas = sorted(({**c, 'deuda_total': c['saldo'] + c['a_facturar']} for c in clientes.values()),
                   key=lambda c: (-c['deuda_total'], c['nombre']))
    return {'columnas': [_col('cliente', 'Cliente'), _col('nombre', 'Nombre'), _col('facturas', 'Facturas con saldo', 'numero'),
                         _col('saldo', 'Saldo facturado', 'gs'), _col('vencido', 'De eso, vencido', 'gs'),
                         _col('dias_atraso', 'Mayor atraso (días)', 'numero'), _col('a_facturar', 'Consumo sin facturar', 'gs'),
                         _col('deuda_total', 'Deuda total', 'gs')],
            'filas': filas, 'totales': _sumar(filas, ['facturas', 'saldo', 'vencido', 'a_facturar', 'deuda_total'])}


TRAMOS = [('Por vencer', None, 0), ('1 a 30 días', 1, 30), ('31 a 60 días', 31, 60), ('61 a 90 días', 61, 90),
          ('Más de 90 días', 91, None)]


def antiguedad_deuda(institucion, f: Filtros):
    hoy = timezone.localdate()
    tramos = {t[0]: {'tramo': t[0], 'facturas': 0, 'clientes': set(), 'saldo': CERO} for t in TRAMOS}
    for fac in _facturas_con_saldo(institucion, f):
        dias = (hoy - fac.fecha_vencimiento).days if fac.fecha_vencimiento else 0
        for nombre, minimo, maximo in TRAMOS:
            if (minimo is None and dias <= 0) or (minimo is not None and dias >= minimo and (maximo is None or dias <= maximo)):
                t = tramos[nombre]
                t['facturas'] += 1
                t['clientes'].add(fac.cliente_id)
                t['saldo'] += fac.saldo
                break
    total = sum((t['saldo'] for t in tramos.values()), CERO)
    filas = [{'tramo': t['tramo'], 'facturas': t['facturas'], 'clientes': len(t['clientes']), 'saldo': t['saldo'],
              'porcentaje': round(t['saldo'] * 100 / total, 1) if total else CERO} for t in tramos.values()]
    return {'columnas': [_col('tramo', 'Atraso desde el vencimiento'), _col('facturas', 'Facturas', 'numero'),
                         _col('clientes', 'Clientes', 'numero'), _col('saldo', 'Saldo', 'gs'),
                         _col('porcentaje', '% del total', 'porcentaje')],
            'filas': filas, 'totales': _sumar(filas, ['facturas', 'saldo'])}


# --- Cobros, gastos, caja, integraciones ----------------------------------------------------------------

def recaudacion(institucion, f: Filtros):
    from apps.cobranzas.models import Pago
    consulta = Pago.objects.de(institucion).filter(estado=Pago.Estado.CONFIRMADO).annotate(dia=TruncDate('fecha_hora'))
    consulta = consulta.filter(dia__gte=f.desde, dia__lte=f.hasta)
    if f.cobrador:
        consulta = consulta.filter(usuario__nombre_usuario=f.cobrador)
    agrupar = f.agrupar if f.agrupar in ('fecha', 'cobrador', 'forma') else 'fecha'
    clave, titulo, campos = {
        'fecha': ('dia', 'Fecha', ['dia']),
        'cobrador': ('usuario__nombre_usuario', 'Cobró', ['usuario__nombre_usuario']),
        'forma': ('forma_pago__nombre', 'Forma de pago', ['forma_pago__nombre', 'forma_pago__tipo']),
    }[agrupar]
    filas = []
    for d in (consulta.values(*campos).annotate(
            cobros=Count('pk'), contado=Sum('importe', filter=Q(origen='contado')),
            recibos=Sum('importe', filter=Q(origen='recibo')), total=Sum('importe')).order_by(
            '-dia' if agrupar == 'fecha' else clave)):
        valor = d[clave]
        filas.append({'grupo': valor.isoformat() if agrupar == 'fecha' else valor, 'cobros': d['cobros'],
                      'contado': d['contado'] or CERO, 'recibos': d['recibos'] or CERO, 'total': d['total'] or CERO})
    return {'columnas': [_col('grupo', titulo, 'fecha' if agrupar == 'fecha' else 'texto'),
                         _col('cobros', 'Cobros', 'numero'), _col('contado', 'Facturas contado', 'gs'),
                         _col('recibos', 'Recibos (crédito)', 'gs'), _col('total', 'Total cobrado', 'gs')],
            'filas': filas, 'totales': _sumar(filas, ['cobros', 'contado', 'recibos', 'total'])}


def gastos(institucion, f: Filtros):
    from apps.caja.models import Gasto
    from apps.caja.models import AdjuntoGasto
    # Exists (no JOIN): un gasto con varios adjuntos no se cuenta ni se suma dos veces.
    consulta = _rango(Gasto.objects.de(institucion), 'fecha', f).annotate(
        con_adjunto=Exists(AdjuntoGasto.objects.filter(gasto=OuterRef('pk'))))
    filas = []
    for d in (consulta.values('categoria__nombre').annotate(
            confirmados=Count('pk', filter=Q(estado='confirmado')), total=Sum('importe', filter=Q(estado='confirmado')),
            sin_confirmar=Sum('importe', filter=Q(estado='registrado')),
            sin_comprobante=Count('pk', filter=Q(estado='confirmado', numero_comprobante='', con_adjunto=False)))
            .order_by('categoria__nombre')):
        filas.append({'categoria': d['categoria__nombre'], 'confirmados': d['confirmados'], 'total': d['total'] or CERO,
                      'sin_confirmar': d['sin_confirmar'] or CERO, 'sin_comprobante': d['sin_comprobante']})
    return {'columnas': [_col('categoria', 'Categoría'), _col('confirmados', 'Gastos confirmados', 'numero'),
                         _col('total', 'Total confirmado', 'gs'), _col('sin_confirmar', 'Registrado sin confirmar', 'gs'),
                         _col('sin_comprobante', 'Confirmados sin comprobante ni adjunto', 'numero')],
            'filas': filas, 'totales': _sumar(filas, ['confirmados', 'total', 'sin_confirmar', 'sin_comprobante'])}


def cajas(institucion, f: Filtros):
    from apps.caja.models import SesionCaja
    consulta = (SesionCaja.objects.de(institucion).annotate(dia=TruncDate('abierta_en'))
                .filter(dia__gte=f.desde, dia__lte=f.hasta).select_related('caja', 'responsable'))
    if f.estado:
        consulta = consulta.filter(estado=f.estado)
    if f.cobrador:
        consulta = consulta.filter(responsable__nombre_usuario=f.cobrador)
    filas = []
    consulta = consulta.annotate(ing=Sum('movimientos__importe', filter=Q(movimientos__tipo='ingreso')),
                                 egr=Sum('movimientos__importe', filter=Q(movimientos__tipo='egreso')))
    for s in consulta.prefetch_related('declaraciones__forma_pago').order_by('-abierta_en'):
        movs = {'ing': s.ing, 'egr': s.egr}
        diferencias = [d for d in s.declaraciones.all() if d.diferencia != 0]
        filas.append({'sesion': s.referencia, 'caja': s.caja.Code, 'cajero': s.responsable.nombre_usuario,
                      'abierta': timezone.localtime(s.abierta_en).strftime('%Y-%m-%d %H:%M'),
                      'cerrada': timezone.localtime(s.cerrada_en).strftime('%Y-%m-%d %H:%M') if s.cerrada_en else '',
                      'estado': s.get_estado_display(), 'ingresos': movs['ing'] or CERO, 'egresos': movs['egr'] or CERO,
                      'diferencias': ' · '.join(f'{d.forma_pago.nombre} {d.diferencia:,.0f}'.replace(',', '.')
                                                for d in diferencias) or ('Sin diferencia' if s.cerrada_en else '')})
    return {'columnas': [_col('sesion', 'Sesión'), _col('caja', 'Caja'), _col('cajero', 'Cajero'),
                         _col('abierta', 'Apertura'), _col('cerrada', 'Cierre'), _col('estado', 'Estado'),
                         _col('ingresos', 'Ingresos', 'gs'), _col('egresos', 'Egresos', 'gs'),
                         _col('diferencias', 'Diferencias por forma de pago')],
            'filas': filas, 'totales': _sumar(filas, ['ingresos', 'egresos'])}


def integraciones(institucion, f: Filtros):
    from apps.facturacion.models import SolicitudElectronica
    filas = []
    for d in (SolicitudElectronica.objects.de(institucion).values('estado').annotate(
            cantidad=Count('pk'), primera=Min('creado_en'), ultima=Max('actualizado_en')).order_by('estado')):
        filas.append({'estado': dict(SolicitudElectronica.Estado.choices).get(d['estado'], d['estado']),
                      'cantidad': d['cantidad'],
                      'primera': timezone.localtime(d['primera']).strftime('%Y-%m-%d %H:%M') if d['primera'] else '',
                      'ultima': timezone.localtime(d['ultima']).strftime('%Y-%m-%d %H:%M') if d['ultima'] else ''})
    return {'columnas': [_col('estado', 'Estado de la factura electrónica'), _col('cantidad', 'Cantidad', 'numero'),
                         _col('primera', 'Más antigua'), _col('ultima', 'Última novedad')],
            'filas': filas, 'totales': _sumar(filas, ['cantidad'])}


@dataclass
class Informe:
    codigo: str
    titulo: str
    grupo: str
    definicion: str
    permisos: tuple
    funcion: object
    filtros: tuple = ()
    agrupaciones: list = field(default_factory=list)


FECHAS = ('desde', 'hasta')
PERIODOS = ('periodo_desde', 'periodo_hasta')
TERRITORIO = ('zona', 'barrio')

INFORMES = [
    Informe('conexiones', 'Conexiones por zona y barrio', 'Padrón',
            'Estado actual de las conexiones. «Total» no incluye las archivadas; «Sin ubicación» cuenta las pendientes '
            'de ubicar y las que no tienen coordenadas.', ('padron.consultar',), conexiones, TERRITORIO),
    Informe('lecturas', 'Avance de lecturas por recorrido', 'Lecturas',
            'Por recorrido: conexiones asignadas, leídas (con lectura confirmada), en revisión (sin confirmada) y '
            'pendientes (el resto).', ('lecturas.consultar',), lecturas, PERIODOS + TERRITORIO + ('cobrador',)),
    Informe('consumo', 'Consumo por período, zona y barrio', 'Lecturas',
            'Suma del consumo (m³) de las lecturas CONFIRMADAS de cada período; el promedio es por lectura.',
            ('lecturas.consultar', 'liquidaciones.consultar'), consumo, PERIODOS + TERRITORIO),
    Informe('liquidaciones', 'Liquidaciones por período', 'Facturación',
            'Liquidaciones VIGENTES (las anuladas no cuentan). Es lo calculado por el consumo, todavía no facturado ni '
            'cobrado.', ('liquidaciones.consultar',), liquidaciones, PERIODOS + TERRITORIO),
    Informe('facturas', 'Facturas emitidas', 'Facturación',
            'Lo FACTURADO por fecha de emisión (facturas vigentes: emitidas o en trámite). No es dinero cobrado: ver '
            '«Recaudación». Las anuladas se cuentan aparte.', ('facturacion.consultar',), facturas, FECHAS,
            [('dia', 'Por día'), ('mes', 'Por mes')]),
    Informe('saldos_clientes', 'Saldos por cliente', 'Cobranzas',
            'Deuda a hoy: saldo de las facturas a crédito (total menos pagos vigentes), cuánto de eso está vencido, y '
            'el consumo liquidado que todavía no se facturó. Con zona o barrio: clientes con alguna conexión ahí (se '
            'muestra toda su deuda).', ('cobranzas.consultar', 'facturacion.consultar'),
            saldos_clientes, TERRITORIO),
    Informe('antiguedad_deuda', 'Antigüedad de la deuda', 'Cobranzas',
            'Saldo de las facturas a crédito según los días transcurridos desde su vencimiento (a hoy).',
            ('cobranzas.consultar', 'facturacion.consultar'), antiguedad_deuda, TERRITORIO),
    Informe('recaudacion', 'Recaudación', 'Cobranzas',
            'Dinero efectivamente COBRADO por la fecha del cobro: pagos confirmados (contado y recibos). Los revertidos '
            '(recibos o facturas contado anulados) no cuentan.', ('cobranzas.consultar',), recaudacion,
            FECHAS + ('cobrador',), [('fecha', 'Por fecha'), ('cobrador', 'Por quien cobró'), ('forma', 'Por forma de pago')]),
    Informe('gastos', 'Gastos referenciales', 'Caja y gastos',
            'Gastos por categoría según su fecha. Solo los CONFIRMADOS salieron de la caja; los registrados sin '
            'confirmar se muestran aparte.', ('gastos.consultar', 'gastos.confirmar'), gastos, FECHAS),
    Informe('cajas', 'Aperturas, cierres y diferencias de caja', 'Caja y gastos',
            'Sesiones de caja abiertas en el rango, con sus ingresos, egresos y las diferencias declaradas al cerrar '
            '(por forma de pago). Filtre «en revisión» para ver las pendientes.', ('caja.supervisar',), cajas,
            FECHAS + ('cobrador', 'estado')),
    Informe('integraciones', 'Estado de la facturación electrónica', 'Integraciones',
            'Solicitudes al proveedor de factura electrónica por estado. «Estado desconocido» exige consultar al '
            'proveedor antes de cualquier reintento.', ('facturacion.consultar', 'facturacion.emitir'), integraciones),
]
POR_CODIGO = {i.codigo: i for i in INFORMES}


def disponibles(permisos: set) -> list[Informe]:
    return [i for i in INFORMES if any(p in permisos for p in i.permisos)]
