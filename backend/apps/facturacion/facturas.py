"""
Emisión de facturas (Fase 5).

Decisiones (21/10/2026): la factura se genera cuando el usuario viene a pagar; puede incluir una o más liquidaciones
de las conexiones del cliente; cada liquidación va ENTERA y en UNA sola factura (no hay facturación parcial: para
pagar en partes se emite a crédito). La modalidad (autoimpresa o electrónica) la fija la plataforma por institución.
Fase 6: una factura CONTADO registra su pago en el mismo paso (con la forma de pago); las de crédito se cobran después
con recibos (`apps.cobranzas`).
"""
import secrets
import uuid
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Exists, F, OuterRef, Sum
from django.utils import timezone

from apps.auditoria.servicios import registrar
from apps.tarifas.models import Liquidacion
from comun.errores import ErrorNegocio
from comun.modelos import validar_misma_institucion

from . import electronica
from .models import (AsignacionFacturaLiquidacion, Factura, LineaFactura, ProveedorFacturacion, PuntoExpedicion,
                     RegistroIntegracion, SolicitudElectronica, TipoDocumento)
from .servicios import tomar_sernr

ALFABETO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
CERO = Decimal('0')
S = SolicitudElectronica.Estado


def _nueva_referencia(institucion) -> str:
    for _ in range(20):
        ref = 'F-' + ''.join(secrets.choice(ALFABETO) for _ in range(8))
        if not Factura.objects.filter(institucion=institucion, referencia=ref).exists():
            return ref
    raise RuntimeError('No se pudo generar la referencia.')


def pendientes_de_facturar(institucion, *, cliente=None, conexion=None):
    """Liquidaciones vigentes que todavía no están en una factura vigente."""
    facturada = AsignacionFacturaLiquidacion.objects.filter(liquidacion=OuterRef('pk'), estado='vigente')
    consulta = (Liquidacion.objects.de(institucion).filter(estado=Liquidacion.Estado.VIGENTE)
                .exclude(Exists(facturada)).select_related('conexion__cliente', 'tarifa', 'lectura'))
    if cliente is not None:
        consulta = consulta.filter(conexion__cliente=cliente)
    if conexion is not None:
        consulta = consulta.filter(conexion=conexion)
    return consulta.order_by('periodo', 'conexion__Code')


def foto_factura(f: Factura) -> dict:
    return {'referencia': f.referencia, 'numero': f.numero_impreso, 'timbrado': f.timbrado, 'cliente': f.cliente.Code,
            'condicion': f.condicion, 'fecha_emision': f.fecha_emision.isoformat(), 'total': str(f.total),
            'estado': f.estado, 'liquidaciones': [a.liquidacion.numero for a in f.asignaciones.all()]}


def _repartir_iva(lineas_liq, iva_total: Decimal, tasa: str) -> dict:
    """Reparte el IVA de una tasa (calculado sobre el subtotal de la liquidación) entre sus líneas, sin perder un
    guaraní por redondeo: la última línea gravada se lleva la diferencia."""
    gravadas = [l for l in lineas_liq if l.iva == tasa and l.importe]
    subtotal = sum((l.importe for l in gravadas), CERO)
    reparto, acumulado = {}, CERO
    for n, linea in enumerate(gravadas):
        if n == len(gravadas) - 1:
            parte = iva_total - acumulado
        else:
            parte = (iva_total * linea.importe / subtotal).quantize(Decimal('1'), rounding=ROUND_HALF_UP) if subtotal else CERO
        reparto[linea.pk] = parte
        acumulado += parte
    return reparto


def _verificar_modalidad(institucion):
    from apps.plataforma.models import Institucion
    if institucion.modalidad_facturacion == Institucion.ModalidadFacturacion.AUTOIMPRESA:
        return Factura.Modalidad.AUTOIMPRESA, None
    if institucion.modalidad_facturacion == Institucion.ModalidadFacturacion.ELECTRONICA:
        proveedor = ProveedorFacturacion.objects.de(institucion).filter(activo=True).first()
        if proveedor is None or electronica.adaptador_para(proveedor) is None:
            raise ErrorNegocio('La facturación electrónica todavía no está conectada con un proveedor: no se puede '
                               'emitir. Consulte con Koape Sistemas.', codigo='proveedor_no_configurado')
        return Factura.Modalidad.ELECTRONICA, proveedor
    raise ErrorNegocio('La institución todavía no tiene habilitada una modalidad de facturación (la configura la '
                       'plataforma según sus habilitaciones fiscales).', codigo='modalidad_no_configurada')


def emitir(*, institucion, cliente, liquidaciones: list, condicion: str, punto: PuntoExpedicion | None = None,
           observaciones: str = '', usuario, forma_pago=None, referencia_externa: str = '', request=None) -> Factura:
    """Emite la factura de las liquidaciones elegidas. Todo o nada; el número sale del rango del punto.
    Contado: `forma_pago` es obligatoria y el pago queda registrado junto con la factura."""
    from apps.cobranzas import servicios as cobranzas
    modalidad, proveedor = _verificar_modalidad(institucion)
    if not liquidaciones:
        raise ErrorNegocio('Elija al menos una liquidación para facturar.')
    if condicion not in Factura.Condicion.values:
        raise ErrorNegocio('Condición de venta inválida.')
    if condicion == Factura.Condicion.CONTADO:
        referencia_externa = cobranzas._validar_forma(institucion, forma_pago, referencia_externa)
        from apps.caja.servicios import sesion_abierta_de
        if sesion_abierta_de(usuario) is None:
            raise ErrorNegocio('Abra su caja antes de cobrar (menú Caja → Mi caja).', codigo='caja_cerrada')
    validar_misma_institucion(institucion, cliente, punto, *liquidaciones)
    if punto is None:
        activos = list(PuntoExpedicion.objects.de(institucion).filter(activo=True)[:2])
        if len(activos) != 1:
            raise ErrorNegocio('Elija el punto de expedición.' if activos else 'No hay puntos de expedición activos.')
        punto = activos[0]
    hoy = timezone.localdate()

    with transaction.atomic():
        bloqueadas = list(Liquidacion.objects.select_for_update().filter(pk__in=[q.pk for q in liquidaciones])
                          .select_related('conexion', 'tarifa').order_by('periodo', 'pk'))
        if len(bloqueadas) != len({q.pk for q in liquidaciones}):
            raise ErrorNegocio('Alguna liquidación no existe.')
        for q in bloqueadas:
            if q.estado != Liquidacion.Estado.VIGENTE:
                raise ErrorNegocio(f'La liquidación {q.numero} está anulada.')
            if q.conexion.cliente_id != cliente.pk:
                raise ErrorNegocio(f'La liquidación {q.numero} es de una conexión de otro titular.')
            if q.asignaciones.filter(estado='vigente').exists():
                raise ErrorNegocio(f'La liquidación {q.numero} ya está facturada.', codigo='ya_facturada')
        sernr, rango = tomar_sernr(punto, TipoDocumento.FACTURA, institucion=institucion, fecha=hoy)
        if modalidad == Factura.Modalidad.AUTOIMPRESA and not rango.timbrado:
            raise ErrorNegocio(f'El rango {rango.Code} no tiene número de timbrado: cárguelo antes de facturar.')
        factura = Factura(
            institucion=institucion, punto=punto, timbrado=rango.timbrado, SerNr=sernr, referencia=_nueva_referencia(institucion),
            modalidad=modalidad, rango=rango, timbrado_vigencia_desde=rango.vigencia_desde,
            timbrado_vigencia_hasta=rango.vigencia_hasta, cliente=cliente, cliente_nombre=cliente.nombre,
            cliente_documento=cliente.documento, cliente_direccion=cliente.direccion_referencia, condicion=condicion,
            fecha_emision=hoy,
            fecha_vencimiento=hoy + timedelta(days=institucion.dias_vencimiento_credito) if condicion == 'credito' else None,
            subtotal_exento=CERO, subtotal_iva5=CERO, subtotal_iva10=CERO, iva5=CERO, iva10=CERO, total=CERO,
            estado=Factura.Estado.EMITIDA if modalidad == Factura.Modalidad.AUTOIMPRESA else Factura.Estado.EN_TRAMITE,
            observaciones=observaciones.strip(), emitida_por=usuario,
        )
        factura.save()
        orden = 0
        for q in bloqueadas:
            lineas_liq = list(q.lineas.all())
            reparto = {**_repartir_iva(lineas_liq, q.iva10, '10'), **_repartir_iva(lineas_liq, q.iva5, '5')}
            for l in lineas_liq:
                if not l.importe:
                    continue  # líneas en cero (ej. sin excedente) no se imprimen
                parte = reparto.get(l.pk, CERO)
                LineaFactura.objects.create(
                    institucion=institucion, factura=factura, orden=orden, liquidacion=q,
                    descripcion=f'{l.concepto} · {q.conexion.Code} · {q.periodo}', tipo=l.tipo, cantidad=l.cantidad,
                    precio_unitario=l.precio, iva=l.iva, importe=l.importe, importe_iva=parte, total_linea=l.importe + parte)
                orden += 1
            AsignacionFacturaLiquidacion.objects.create(institucion=institucion, factura=factura, liquidacion=q,
                                                        importe=q.total)
            factura.subtotal_exento += q.subtotal_exento
            factura.subtotal_iva5 += q.subtotal_iva5 + q.iva5
            factura.subtotal_iva10 += q.subtotal_iva10 + q.iva10
            factura.iva5 += q.iva5
            factura.iva10 += q.iva10
            factura.total += q.total
        factura.save()
        if condicion == Factura.Condicion.CONTADO:
            cobranzas.registrar_pago_contado(factura, forma_pago=forma_pago, referencia_externa=referencia_externa,
                                             usuario=usuario, request=request)
        if modalidad == Factura.Modalidad.ELECTRONICA:
            SolicitudElectronica.objects.create(institucion=institucion, factura=factura, proveedor=proveedor,
                                                id_solicitud=uuid.uuid4())
        registrar('factura_emitida', request=request, entidad='factura', entidad_id=factura.referencia,
                  despues=foto_factura(factura))
    # La solicitud ya quedó registrada (confirmada en la base): recién ahora se llama al proveedor.
    if modalidad == Factura.Modalidad.ELECTRONICA:
        enviar_electronica(factura, request=request)
        factura.refresh_from_db()
    return factura


def anular(factura: Factura, *, motivo: str, usuario, request=None) -> Factura:
    """Anula una factura autoimpresa emitida: queda en el historial y sus liquidaciones vuelven a quedar para facturar."""
    motivo = (motivo or '').strip()
    if not motivo:
        raise ErrorNegocio('Indique el motivo de la anulación.')
    with transaction.atomic():
        factura = Factura.objects.select_for_update().get(pk=factura.pk)
        if factura.estado == Factura.Estado.ANULADA:
            raise ErrorNegocio('La factura ya está anulada.')
        if factura.modalidad == Factura.Modalidad.ELECTRONICA:
            raise ErrorNegocio('Una factura electrónica se cancela con el procedimiento del proveedor (se habilita al '
                               'conectar el proveedor).')
        from apps.cobranzas import servicios as cobranzas
        recibos = cobranzas.recibos_vigentes_de(factura)
        if recibos:
            raise ErrorNegocio(f'La factura tiene cobros con recibo ({", ".join(recibos)}): anule antes esos recibos.',
                               codigo='tiene_recibos')
        antes = foto_factura(factura)
        factura.estado = Factura.Estado.ANULADA
        factura.anulada_por, factura.anulada_en, factura.motivo_anulacion = usuario, timezone.now(), motivo
        factura.save()
        factura.asignaciones.filter(estado='vigente').update(estado=AsignacionFacturaLiquidacion.Estado.ANULADA)
        # Contado: el pago que se registró con la factura queda revertido (se conserva el original).
        cobranzas.revertir_pagos_contado(factura, motivo=f'Factura {factura.numero_impreso} anulada: {motivo}',
                                         usuario=usuario, request=request)
        registrar('factura_anulada', request=request, entidad='factura', entidad_id=factura.referencia, motivo=motivo,
                  antes=antes, despues=foto_factura(factura))
    return factura


# --- Electrónica --------------------------------------------------------------------------------------

ESTADO_FACTURA = {S.APROBADA: Factura.Estado.EMITIDA, S.RECHAZADA: Factura.Estado.RECHAZADA}


def _registrar_integracion(solicitud, operacion, antes, despues='', detalle=None, error=''):
    RegistroIntegracion.objects.create(institucion=solicitud.institucion, solicitud=solicitud, operacion=operacion,
                                       estado_antes=antes, estado_despues=despues, detalle=detalle or {}, error=error)


ESTADOS_DEL_PROVEEDOR = {S.ENVIADA, S.EN_PROCESO, S.APROBADA, S.RECHAZADA}


def _aplicar(solicitud, resultado: electronica.Resultado, operacion: str, request=None):
    if resultado.estado not in ESTADOS_DEL_PROVEEDOR:
        # Un adaptador no puede inventar estados: lo que no se entiende queda para consultar.
        _error(solicitud, operacion, S.DESCONOCIDO, f'Respuesta con estado no reconocido: {resultado.estado!r}', request)
        return
    with transaction.atomic():
        solicitud = SolicitudElectronica.objects.select_for_update(of=('self',)).select_related('factura').get(pk=solicitud.pk)
        antes = solicitud.estado
        solicitud.estado = resultado.estado
        solicitud.numero_proveedor = resultado.numero_proveedor or solicitud.numero_proveedor
        solicitud.ultima_respuesta = resultado.respuesta
        solicitud.ultimo_error = '' if resultado.estado != S.RECHAZADA else resultado.mensaje
        solicitud.save()
        factura = solicitud.factura
        nuevo = ESTADO_FACTURA.get(resultado.estado)
        if nuevo and factura.estado == Factura.Estado.EN_TRAMITE:
            factura.estado = nuevo
            if resultado.cdc:
                factura.cdc = resultado.cdc
            factura.datos_fiscales = resultado.respuesta
            factura.save()
            if nuevo == Factura.Estado.RECHAZADA:
                # Rechazada: no es un documento fiscal; sus liquidaciones vuelven a quedar para facturar.
                factura.asignaciones.filter(estado='vigente').update(estado=AsignacionFacturaLiquidacion.Estado.ANULADA)
                from apps.cobranzas import servicios as cobranzas
                cobranzas.revertir_pagos_contado(factura, motivo='Factura electrónica rechazada por el proveedor',
                                                 request=request)
        _registrar_integracion(solicitud, operacion, antes, resultado.estado, resultado.respuesta, resultado.mensaje)
        registrar(f'factura_electronica_{operacion}', request=request, entidad='factura', entidad_id=factura.referencia,
                  antes={'estado': antes}, despues={'estado': resultado.estado})


def _error(solicitud, operacion, estado, mensaje, request=None):
    with transaction.atomic():
        solicitud = SolicitudElectronica.objects.select_for_update().get(pk=solicitud.pk)
        antes = solicitud.estado
        solicitud.estado, solicitud.ultimo_error = estado, mensaje[:2000]
        solicitud.save()
        _registrar_integracion(solicitud, operacion, antes, estado, error=mensaje[:2000])


def enviar_electronica(factura: Factura, *, request=None) -> None:
    """Envía (o reenvía, con el MISMO id de solicitud) una factura pendiente o con error recuperable."""
    # Se «toma» la solicitud con bloqueo y se marca ENVIADA ANTES de llamar al proveedor (y se confirma): si el proceso
    # se corta a mitad de la llamada, o dos cajeros pulsan «Reintentar» a la vez, nadie vuelve a enviarla: se consulta.
    with transaction.atomic():
        solicitud = SolicitudElectronica.objects.select_for_update(of=('self',)).select_related('proveedor').get(factura=factura)
        if solicitud.estado not in (S.PENDIENTE, S.ERROR):
            raise ErrorNegocio(f'La solicitud está «{solicitud.get_estado_display()}»: no se reenvía. '
                               'Use «Consultar estado».', codigo='no_reenviable')
        adaptador = electronica.adaptador_para(solicitud.proveedor)
        if adaptador is None:
            raise ErrorNegocio('El proveedor electrónico no está conectado.', codigo='proveedor_no_configurado')
        antes = solicitud.estado
        SolicitudElectronica.objects.filter(pk=solicitud.pk).update(intentos=F('intentos') + 1, estado=S.ENVIADA)
        _registrar_integracion(solicitud, 'tomar_envio', antes, S.ENVIADA)
    try:
        resultado = adaptador.enviar(str(solicitud.id_solicitud), electronica.documento_de(factura))
    except electronica.ErrorProveedor as e:
        # El proveedor contestó que no lo procesó: se puede reintentar con el mismo id.
        _error(solicitud, 'enviar', S.ERROR, str(e), request)
        return
    except Exception as e:  # ErrorTemporal, corte, error inesperado del adaptador
        # No sabemos si llegó: NO se reenvía a ciegas, queda para consultar.
        _error(solicitud, 'enviar', S.DESCONOCIDO, f'Sin respuesta segura del proveedor: {e}', request)
        return
    _aplicar(solicitud, resultado, 'enviar', request)


def consultar_electronica(factura: Factura, *, request=None) -> None:
    solicitud = SolicitudElectronica.objects.select_related('proveedor').get(factura=factura)
    if solicitud.estado in (S.APROBADA, S.RECHAZADA, S.ANULADA):
        return
    adaptador = electronica.adaptador_para(solicitud.proveedor)
    if adaptador is None:
        raise ErrorNegocio('El proveedor electrónico no está conectado.', codigo='proveedor_no_configurado')
    try:
        resultado = adaptador.consultar(str(solicitud.id_solicitud), solicitud.numero_proveedor)
    except Exception as e:
        _registrar_integracion(solicitud, 'consultar', solicitud.estado, solicitud.estado, error=str(e)[:2000])
        raise ErrorNegocio(f'No se pudo consultar al proveedor: {e}')
    _aplicar(solicitud, resultado, 'consultar', request)


def deudas_de_conexion(conexion) -> dict:
    """Para el cobrador después de la lectura y para la caja: lo pendiente de facturar y las facturas a crédito con
    saldo. Una factura puede llevar varias conexiones: se informa solo la parte de ESTA conexión, y lo ya pagado de la
    factura se reparte en proporción (los pagos se aplican a la factura, no a cada conexión)."""
    from apps.cobranzas.servicios import pagado_de_factura
    pendientes = pendientes_de_facturar(conexion.institucion, conexion=conexion)
    # Las que están en trámite con el proveedor también cuentan: sus liquidaciones ya no figuran como pendientes.
    facturas = (Factura.objects.de(conexion.institucion).filter(
        condicion=Factura.Condicion.CREDITO, estado__in=[Factura.Estado.EMITIDA, Factura.Estado.EN_TRAMITE],
        asignaciones__liquidacion__conexion=conexion, asignaciones__estado='vigente')
        .annotate(de_la_conexion=Sum('asignaciones__importe'), pagado=pagado_de_factura())
        .select_related('punto').order_by('fecha_emision', 'SerNr'))
    hoy = timezone.localdate()
    lista = []
    for f in facturas:
        saldo_factura = f.total - f.pagado
        if saldo_factura <= 0:
            continue
        saldo = (f.de_la_conexion * saldo_factura / f.total).quantize(Decimal('1'), rounding=ROUND_HALF_UP) \
            if f.total else CERO
        lista.append({'numero': f.numero_impreso, 'fecha_emision': f.fecha_emision.isoformat(),
                      'fecha_vencimiento': f.fecha_vencimiento.isoformat() if f.fecha_vencimiento else None,
                      'importe': f'{f.de_la_conexion:.2f}', 'pagado': f'{f.de_la_conexion - saldo:.2f}',
                      'saldo': f'{saldo:.2f}',
                      'dias_mora': max((hoy - f.fecha_vencimiento).days, 0) if f.fecha_vencimiento else 0})
    return {
        'disponible': True,
        'pendientes_de_facturar': [{'liquidacion': q.numero, 'periodo': q.periodo, 'total': str(q.total)} for q in pendientes],
        'facturas': lista,
        'mensaje': '' if pendientes or lista else 'Sin deudas pendientes.',
    }
