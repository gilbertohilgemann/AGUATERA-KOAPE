"""
Reglas de pagos y recibos (Fase 6). Todo pasa por acá: las vistas no tocan saldos.

Consistencia (sección 18): cada operación bloquea las facturas involucradas (`select_for_update`) y vuelve a calcular
sus saldos DENTRO de la transacción; dos cajeros nunca pueden cobrar a la vez más que el saldo. Un reintento de red con
la misma `clave` devuelve el recibo ya emitido en lugar de crear otro.
"""
import secrets
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import DecimalField, Exists, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.auditoria.servicios import registrar
from apps.facturacion.models import Factura
from apps.plataforma.models import siguiente_numero
from comun.errores import ErrorNegocio
from comun.modelos import validar_misma_institucion

from .models import FORMAS_INICIALES, AplicacionPago, FormaPago, Pago, Recibo

CERO = Decimal('0')
ALFABETO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
DINERO = DecimalField(max_digits=18, decimal_places=2)


# --- Saldos (derivados, nunca guardados) ---------------------------------------------------------------

def pagado_de_factura():
    """Expresión: suma de las aplicaciones VIGENTES de la factura (subconsulta: no multiplica filas)."""
    suma = (AplicacionPago.objects.filter(factura=OuterRef('pk'), estado=AplicacionPago.Estado.VIGENTE)
            .order_by().values('factura').annotate(s=Sum('importe')).values('s'))
    return Coalesce(Subquery(suma, output_field=DINERO), Value(CERO), output_field=DINERO)


def con_saldo(consulta):
    return consulta.annotate(pagado=pagado_de_factura()).annotate(
        saldo=F('total') - F('pagado'))


def pagado(factura) -> Decimal:
    return (AplicacionPago.objects.filter(factura=factura, estado=AplicacionPago.Estado.VIGENTE)
            .aggregate(s=Sum('importe'))['s'] or CERO)


def facturas_con_saldo(institucion, cliente):
    """Facturas a crédito vigentes del cliente que todavía deben algo, la vencida más antigua primero."""
    return (con_saldo(Factura.objects.de(institucion).filter(
        cliente=cliente, condicion=Factura.Condicion.CREDITO, estado=Factura.Estado.EMITIDA))
        .filter(saldo__gt=0).select_related('punto').order_by('fecha_vencimiento', 'fecha_emision', 'SerNr'))


def saldo_cliente(institucion, cliente) -> Decimal:
    return sum((f.saldo for f in facturas_con_saldo(institucion, cliente)), CERO)


def estado_cobro(factura, saldo: Decimal, hoy=None) -> str:
    """Estado DERIVADO (sección 11.5): pagada, parcial, pendiente o vencida."""
    if factura.estado != Factura.Estado.EMITIDA:
        return ''
    if saldo <= 0:
        return 'pagada'
    hoy = hoy or timezone.localdate()
    if factura.fecha_vencimiento and factura.fecha_vencimiento < hoy:
        return 'vencida'
    return 'parcial' if saldo < factura.total else 'pendiente'


def repartir_automatico(facturas: list, importe: Decimal) -> list:
    """Política «la vencida más antigua primero»: [(factura, importe)] en el orden de `facturas`."""
    resto, reparto = importe, []
    for f in facturas:
        if resto <= 0:
            break
        parte = min(resto, f.saldo)
        if parte > 0:
            reparto.append((f, parte))
            resto -= parte
    return reparto


# --- Formas de pago -----------------------------------------------------------------------------------

def crear_formas_iniciales(institucion) -> None:
    for code, nombre, tipo, referencia, orden in FORMAS_INICIALES:
        FormaPago.objects.get_or_create(institucion=institucion, Code=code, defaults={
            'nombre': nombre, 'tipo': tipo, 'requiere_referencia': referencia, 'orden': orden})


def _validar_forma(institucion, forma_pago, referencia_externa: str) -> str:
    if forma_pago is None:
        raise ErrorNegocio('Elija la forma de pago.', codigo='forma_pago_requerida')
    validar_misma_institucion(institucion, forma_pago)
    if not forma_pago.activa:
        raise ErrorNegocio(f'La forma de pago «{forma_pago.nombre}» está desactivada.')
    referencia_externa = (referencia_externa or '').strip()
    if forma_pago.requiere_referencia and not referencia_externa:
        raise ErrorNegocio(f'Indique la referencia de la operación ({forma_pago.nombre}).', codigo='falta_referencia')
    return referencia_externa


def _nueva_referencia(institucion) -> str:
    for _ in range(20):
        ref = 'P-' + ''.join(secrets.choice(ALFABETO) for _ in range(8))
        if not Pago.objects.filter(institucion=institucion, referencia=ref).exists():
            return ref
    raise RuntimeError('No se pudo generar la referencia del pago.')


def _importe(valor) -> Decimal:
    try:
        importe = Decimal(str(valor))
    except Exception:
        raise ErrorNegocio('Importe inválido.')
    if importe <= 0 or importe != importe.to_integral_value():
        raise ErrorNegocio('El importe debe ser un número entero de guaraníes mayor que cero.')
    return importe


def foto_pago(p: Pago) -> dict:
    return {'referencia': p.referencia, 'cliente': p.cliente.Code, 'importe': str(p.importe), 'forma': p.forma_pago.Code,
            'referencia_externa': p.referencia_externa, 'origen': p.origen, 'estado': p.estado,
            'aplicaciones': [{'factura': a.factura.numero_impreso, 'importe': str(a.importe), 'estado': a.estado}
                             for a in p.aplicaciones.select_related('factura__punto')]}


# --- Factura contado: el pago se registra al emitirla ----------------------------------------------------

def registrar_pago_contado(factura: Factura, *, forma_pago, referencia_externa='', usuario, request=None) -> Pago:
    """Se llama DENTRO de la transacción que emite la factura contado: la factura nunca queda impaga."""
    from apps.caja import servicios as caja
    institucion = factura.institucion
    referencia_externa = _validar_forma(institucion, forma_pago, referencia_externa)
    sesion = caja.exigir_sesion(usuario)
    pago = Pago.objects.create(
        institucion=institucion, sesion=sesion, referencia=_nueva_referencia(institucion), cliente=factura.cliente,
        fecha_hora=timezone.now(), importe=factura.total, forma_pago=forma_pago, referencia_externa=referencia_externa,
        origen=Pago.Origen.CONTADO, clave_idempotencia=f'contado:{factura.referencia}', usuario=usuario)
    AplicacionPago.objects.create(institucion=institucion, pago=pago, factura=factura, importe=factura.total,
                                  saldo_anterior=factura.total, usuario=usuario)
    caja.registrar_cobro(pago, sesion)
    registrar('pago_registrado', request=request, usuario=usuario, institucion=institucion, entidad='pago', entidad_id=pago.referencia, despues=foto_pago(pago))
    return pago


def revertir_pagos_contado(factura: Factura, *, motivo: str, usuario=None, request=None) -> None:
    """Al anular (o rechazarse) una factura contado, su pago queda REVERTIDO (se conserva el original).
    Debe llamarse dentro de la transacción que bloqueó la factura."""
    # Sin JOIN ni DISTINCT en la consulta bloqueada: PostgreSQL no admite FOR UPDATE con DISTINCT.
    ids = AplicacionPago.objects.filter(factura=factura).values('pago_id')
    for pago in (Pago.objects.select_for_update().filter(
            pk__in=Subquery(ids), origen=Pago.Origen.CONTADO, estado=Pago.Estado.CONFIRMADO).order_by('pk')):
        _revertir(pago, motivo=motivo, usuario=usuario, request=request)


def _revertir(pago: Pago, *, motivo, usuario, request) -> None:
    from apps.caja import servicios as caja
    antes = foto_pago(pago)
    # Movimiento compensatorio en la caja (el ingreso original no se toca).
    caja.revertir_cobro(pago, usuario=usuario, motivo=motivo)
    pago.estado = Pago.Estado.REVERTIDO
    pago.revertido_por, pago.revertido_en, pago.motivo_reversion = usuario, timezone.now(), motivo
    pago.save()
    pago.aplicaciones.filter(estado=AplicacionPago.Estado.VIGENTE).update(estado=AplicacionPago.Estado.REVERTIDA)
    registrar('pago_revertido', request=request, usuario=usuario, institucion=pago.institucion, entidad='pago',
              entidad_id=pago.referencia, motivo=motivo, antes=antes, despues=foto_pago(pago))


def recibos_vigentes_de(factura: Factura) -> list[str]:
    """Números de los recibos vigentes que pagaron (en parte) la factura: impiden anularla."""
    return [r.numero_impreso for r in Recibo.objects.filter(
        estado=Recibo.Estado.EMITIDO, pago__aplicaciones__factura=factura,
        pago__aplicaciones__estado=AplicacionPago.Estado.VIGENTE).distinct()]


# --- Recibos (facturas a crédito) -----------------------------------------------------------------------

def emitir_recibo(*, institucion, cliente, importe, forma_pago, clave: str, aplicaciones: list | None = None,
                  referencia_externa: str = '', observaciones: str = '', usuario, request=None) -> Recibo:
    """
    Cobra `importe` al cliente y lo aplica a sus facturas a crédito.

    `aplicaciones` = [(factura, importe)] lo indica el cajero. Si viene vacío, se usa la política de la institución:
    automática (vencida más antigua primero) o, si es manual, se exige el reparto. La suma aplicada debe ser igual al
    importe: no hay saldo a favor (decisión 21/10/2026), el vuelto se da en el momento.
    """
    clave = (clave or '').strip()
    if not clave or len(clave) > 64 or clave.startswith('contado:'):
        raise ErrorNegocio('Falta la clave de la operación (reintente desde la pantalla).')
    importe = _importe(importe)
    existente = _recibo_por_clave(institucion, clave)
    if existente is not None:
        return _repetido(existente, cliente, importe, forma_pago)
    validar_misma_institucion(institucion, cliente)
    referencia_externa = _validar_forma(institucion, forma_pago, referencia_externa)
    try:
        with transaction.atomic():
            recibo = _emitir(institucion, cliente, importe, forma_pago, clave, aplicaciones, referencia_externa,
                             (observaciones or '').strip(), usuario, request)
    except IntegrityError:
        # Dos envíos simultáneos con la misma clave: el otro ganó; se devuelve ese recibo.
        existente = _recibo_por_clave(institucion, clave)
        if existente is None:
            raise ErrorNegocio('Esa clave de operación ya se usó.', codigo='clave_repetida')
        return _repetido(existente, cliente, importe, forma_pago)
    if isinstance(recibo, tuple):  # el reintento llegó mientras el primero se confirmaba
        return _repetido(recibo[0], cliente, importe, forma_pago)
    return recibo


def _recibo_por_clave(institucion, clave):
    return (Recibo.objects.de(institucion).select_related('pago', 'cliente')
            .filter(pago__clave_idempotencia=clave).first())


def _repetido(recibo, cliente, importe, forma_pago):
    if recibo.cliente_id != cliente.pk or recibo.importe != importe or recibo.pago.forma_pago_id != forma_pago.pk:
        raise ErrorNegocio('Esa clave de operación ya se usó para otro cobro.', codigo='clave_repetida')
    return recibo


def _emitir(institucion, cliente, importe, forma_pago, clave, aplicaciones, referencia_externa, observaciones,
            usuario, request):
    pedidas = []
    for factura, parte in (aplicaciones or []):
        validar_misma_institucion(institucion, factura)
        pedidas.append((factura.pk, _importe(parte)))
    if len({pk for pk, _ in pedidas}) != len(pedidas):
        raise ErrorNegocio('Una factura figura dos veces en el reparto.')
    # Bloqueo de TODAS las facturas a crédito del cliente (orden fijo: sin interbloqueos) y saldos recalculados.
    bloqueadas = list(Factura.objects.select_for_update().filter(
        institucion=institucion, cliente=cliente, condicion=Factura.Condicion.CREDITO).order_by('pk'))
    # Con las facturas bloqueadas, se vuelve a buscar la clave: un reintento que esperó el bloqueo encuentra el recibo
    # ya confirmado por el primer envío y lo devuelve (en vez de rechazarlo por falta de saldo).
    ya = _recibo_por_clave(institucion, clave)
    if ya is not None:
        return (ya,)
    por_pk = {f.pk: f for f in bloqueadas}
    vigentes = list(facturas_con_saldo(institucion, cliente))
    saldos = {f.pk: f.saldo for f in vigentes}
    total_saldo = sum(saldos.values(), CERO)
    if importe > total_saldo:
        raise ErrorNegocio(f'El importe supera la deuda a crédito del cliente (Gs. {total_saldo:,.0f}).'.replace(',', '.'),
                           codigo='supera_saldo')
    if not pedidas:
        if institucion.aplicacion_pagos != 'automatica':
            raise ErrorNegocio('Indique cuánto se aplica a cada factura.', codigo='reparto_requerido')
        pedidas = [(f.pk, parte) for f, parte in repartir_automatico(vigentes, importe)]
    for pk, parte in pedidas:
        factura = por_pk.get(pk)
        if factura is None:
            raise ErrorNegocio('Solo se cobran con recibo las facturas a crédito del mismo cliente.')
        if pk not in saldos:
            raise ErrorNegocio(f'La factura {factura.numero_impreso} no tiene saldo pendiente.', codigo='sin_saldo')
        if parte > saldos[pk]:
            raise ErrorNegocio(f'A la factura {factura.numero_impreso} se le aplica más que su saldo '
                               f'(Gs. {saldos[pk]:,.0f}).'.replace(',', '.'), codigo='supera_saldo')
    if sum((p for _, p in pedidas), CERO) != importe:
        raise ErrorNegocio('La suma aplicada a las facturas debe ser igual al importe recibido.', codigo='reparto_distinto')

    from apps.caja import servicios as caja
    sesion = caja.exigir_sesion(usuario)
    ahora = timezone.now()
    pago = Pago.objects.create(
        institucion=institucion, sesion=sesion, referencia=_nueva_referencia(institucion), cliente=cliente,
        fecha_hora=ahora,
        importe=importe, forma_pago=forma_pago, referencia_externa=referencia_externa, origen=Pago.Origen.RECIBO,
        observaciones=observaciones, clave_idempotencia=clave, usuario=usuario)
    for pk, parte in pedidas:
        AplicacionPago.objects.create(institucion=institucion, pago=pago, factura=por_pk[pk], importe=parte,
                                      saldo_anterior=saldos[pk], usuario=usuario)
    recibo = Recibo.objects.create(
        institucion=institucion, numero=siguiente_numero(institucion, 'recibo'), pago=pago, cliente=cliente,
        cliente_nombre=cliente.nombre, cliente_documento=cliente.documento, fecha_hora=ahora, importe=importe,
        saldo_restante=total_saldo - importe)
    caja.registrar_cobro(pago, sesion)
    registrar('recibo_emitido', request=request, usuario=usuario, institucion=institucion, entidad='recibo', entidad_id=recibo.numero_impreso,
              despues={'numero': recibo.numero_impreso, **foto_pago(pago)})
    return recibo


def anular_recibo(recibo: Recibo, *, motivo: str, usuario, request=None) -> Recibo:
    """El recibo queda ANULADO con su número y el pago REVERTIDO: las facturas recuperan su saldo."""
    motivo = (motivo or '').strip()
    if not motivo:
        raise ErrorNegocio('Indique el motivo de la anulación.')
    with transaction.atomic():
        recibo = Recibo.objects.select_for_update(of=('self',)).select_related('pago').get(pk=recibo.pk)
        if recibo.estado == Recibo.Estado.ANULADO:
            raise ErrorNegocio('El recibo ya está anulado.')
        # Las facturas afectadas se bloquean igual que al cobrar (mismo orden) para no cruzarse con otro cobro.
        ids = AplicacionPago.objects.filter(pago=recibo.pago).values('factura_id')
        list(Factura.objects.select_for_update().filter(pk__in=Subquery(ids)).order_by('pk'))
        recibo.estado = Recibo.Estado.ANULADO
        recibo.anulado_por, recibo.anulado_en, recibo.motivo_anulacion = usuario, timezone.now(), motivo
        recibo.save()
        _revertir(recibo.pago, motivo=f'Recibo {recibo.numero_impreso} anulado: {motivo}', usuario=usuario,
                  request=request)
        registrar('recibo_anulado', request=request, usuario=usuario, institucion=recibo.institucion, entidad='recibo', entidad_id=recibo.numero_impreso, motivo=motivo)
    return recibo


# --- Estado de deuda de una conexión (filtros del padrón y del mapa, sección 8.2) -------------------------------

def condiciones_deuda_conexion(hoy=None) -> dict:
    """
    Expresiones `Exists` sobre `Conexion` (definiciones explícitas, D50):
    - `sin_facturar`: tiene consumos liquidados que todavía no están en una factura vigente.
    - `con_saldo`: está en una factura a crédito vigente (emitida o en trámite) que todavía debe algo.
    - `vencida`: está en una factura a crédito con saldo cuyo vencimiento ya pasó.
    Con deuda = sin_facturar o con_saldo · Morosa = vencida · Al día = ninguna de las dos primeras.
    Tener saldo no es estar en mora: un consumo sin facturar o una factura que todavía no venció es deuda, no mora.
    """
    from apps.facturacion.models import AsignacionFacturaLiquidacion
    from apps.tarifas.models import Liquidacion
    hoy = hoy or timezone.localdate()
    facturada = AsignacionFacturaLiquidacion.objects.filter(liquidacion=OuterRef('pk'), estado='vigente')
    sin_facturar = Exists(Liquidacion.objects.filter(conexion=OuterRef('pk'), estado=Liquidacion.Estado.VIGENTE)
                          .exclude(Exists(facturada)))
    facturas = con_saldo(Factura.objects.filter(
        condicion=Factura.Condicion.CREDITO, estado__in=[Factura.Estado.EMITIDA, Factura.Estado.EN_TRAMITE],
        asignaciones__liquidacion__conexion=OuterRef('pk'), asignaciones__estado='vigente')).filter(saldo__gt=0)
    return {'sin_facturar': sin_facturar, 'con_saldo': Exists(facturas),
            'vencida': Exists(facturas.filter(fecha_vencimiento__lt=hoy))}


def filtrar_por_deuda(consulta, valor: str):
    """`deuda`: con · al_dia · morosa · sin_facturar (cualquier otro valor no filtra)."""
    if valor not in ('con', 'al_dia', 'morosa', 'sin_facturar'):
        return consulta
    c = condiciones_deuda_conexion()
    if valor == 'con':
        return consulta.filter(c['sin_facturar'] | c['con_saldo'])
    if valor == 'al_dia':
        return consulta.exclude(c['sin_facturar']).exclude(c['con_saldo'])
    if valor == 'morosa':
        return consulta.filter(c['vencida'])
    return consulta.filter(c['sin_facturar'])
