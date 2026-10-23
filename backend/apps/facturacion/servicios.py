"""
Reglas de los puntos de expedición, de los rangos de numeración y de la asignación de `SerNr`.
"""
from django.db import IntegrityError, transaction
from django.db.models import F, Max, Q
from django.utils import timezone

from apps.auditoria.servicios import registrar
from comun.codigos import code_valido
from comun.errores import ErrorNegocio
from comun.modelos import validar_misma_institucion

from .models import PuntoExpedicion, RangoNumeracion, TipoDocumento


def foto_punto(p: PuntoExpedicion) -> dict:
    return {'Code': p.Code, 'establecimiento': p.establecimiento, 'punto': p.punto, 'nombre': p.nombre,
            'direccion': p.direccion, 'activo': p.activo}


def foto_rango(r: RangoNumeracion) -> dict:
    return {'Code': r.Code, 'punto': r.punto.Code, 'tipo_documento': r.tipo_documento, 'timbrado': r.timbrado,
            'desde': r.desde, 'hasta': r.hasta,
            'vigencia_desde': r.vigencia_desde.isoformat() if r.vigencia_desde else None,
            'vigencia_hasta': r.vigencia_hasta.isoformat() if r.vigencia_hasta else None, 'activo': r.activo}


def _guardar(objeto, mensaje_duplicado: str):
    try:
        with transaction.atomic():
            objeto.save()
    except IntegrityError:
        raise ErrorNegocio(mensaje_duplicado)


# --- Puntos de expedición ----------------------------------------------------------------------

def crear_punto(*, institucion, datos: dict, request=None) -> PuntoExpedicion:
    datos = dict(datos)
    code = code_valido(datos.pop('Code', ''))
    with transaction.atomic():
        punto = PuntoExpedicion(institucion=institucion, Code=code, **datos)
        _guardar(punto, 'Ya existe un punto de expedición con ese código o con ese establecimiento y punto.')
        registrar('punto_expedicion_creado', request=request, entidad='punto_expedicion', entidad_id=punto.Code,
                  despues=foto_punto(punto))
    return punto


def actualizar_punto(punto: PuntoExpedicion, datos: dict, *, request=None) -> PuntoExpedicion:
    datos = dict(datos)
    datos.pop('Code', None)
    with transaction.atomic():
        punto = PuntoExpedicion.objects.select_for_update().get(pk=punto.pk)
        cambia_numero = any(c in datos and datos[c] != getattr(punto, c) for c in ('establecimiento', 'punto'))
        if cambia_numero and punto.rangos.filter(ultimo_usado__isnull=False).exists():
            raise ErrorNegocio('Este punto ya emitió documentos: su establecimiento y número no se cambian.')
        antes = foto_punto(punto)
        for campo, valor in datos.items():
            setattr(punto, campo, valor)
        _guardar(punto, 'Ya existe un punto de expedición con ese establecimiento y punto.')
        despues = foto_punto(punto)
        accion = 'punto_expedicion_modificado'
        if antes['activo'] != despues['activo']:
            accion = 'punto_expedicion_' + ('restaurado' if despues['activo'] else 'desactivado')
        registrar(accion, request=request, entidad='punto_expedicion', entidad_id=punto.Code, antes=antes,
                  despues=despues)
    return punto


# --- Rangos de numeración ----------------------------------------------------------------------

def _validar_rango(rango: RangoNumeracion):
    if rango.desde < 1:
        raise ErrorNegocio('El rango empieza en 1 o más.')
    if rango.hasta < rango.desde:
        raise ErrorNegocio('«Hasta» no puede ser menor que «desde».')
    if rango.vigencia_desde and rango.vigencia_hasta and rango.vigencia_hasta < rango.vigencia_desde:
        raise ErrorNegocio('La vigencia termina antes de empezar.')
    if rango.ultimo_usado is not None and rango.hasta < rango.ultimo_usado:
        raise ErrorNegocio('«Hasta» no puede ser menor que un número ya emitido con este rango.')
    # Mismo punto, tipo y timbrado: los rangos no pueden superponerse (el SerNr se repetiría).
    superpuestos = RangoNumeracion.objects.filter(
        institucion_id=rango.institucion_id, punto_id=rango.punto_id, tipo_documento=rango.tipo_documento,
        timbrado=rango.timbrado, desde__lte=rango.hasta, hasta__gte=rango.desde,
    ).exclude(pk=rango.pk)
    otro = superpuestos.first()
    if otro is not None:
        raise ErrorNegocio(f'Se superpone con el rango {otro.Code} ({otro.desde}–{otro.hasta}) del mismo punto, '
                           'tipo de documento y timbrado.')
    # La numeración nunca retrocede: lo que este rango todavía puede entregar debe ir después del mayor número
    # ya emitido con el mismo punto, tipo y timbrado.
    tope = _mayor_emitido(rango.punto_id, rango.tipo_documento, rango.timbrado, excluir=rango.pk)
    siguiente = rango.desde if rango.ultimo_usado is None else rango.ultimo_usado + 1
    if tope is not None and siguiente <= rango.hasta and siguiente <= tope:
        raise ErrorNegocio(f'Ya se emitieron números hasta el {tope} con el mismo punto, tipo de documento y '
                           f'timbrado: los números nuevos deben empezar después del {tope}.')
    # En una misma fecha, un punto usa un solo timbrado por tipo de documento.
    if rango.activo:
        conflicto = RangoNumeracion.objects.filter(
            punto_id=rango.punto_id, tipo_documento=rango.tipo_documento, activo=True,
        ).exclude(pk=rango.pk).exclude(timbrado=rango.timbrado)
        if rango.vigencia_hasta is not None:
            conflicto = conflicto.filter(Q(vigencia_desde__isnull=True) | Q(vigencia_desde__lte=rango.vigencia_hasta))
        if rango.vigencia_desde is not None:
            conflicto = conflicto.filter(Q(vigencia_hasta__isnull=True) | Q(vigencia_hasta__gte=rango.vigencia_desde))
        otro = conflicto.first()
        if otro is not None:
            raise ErrorNegocio(f'Su vigencia se cruza con el rango {otro.Code} de otro timbrado ({otro.timbrado or "sin timbrado"}): '
                               'ajuste las fechas de vigencia o desactive uno de los dos.')


def _mayor_emitido(punto_id, tipo_documento, timbrado, excluir=None):
    consulta = RangoNumeracion.objects.filter(punto_id=punto_id, tipo_documento=tipo_documento, timbrado=timbrado)
    if excluir is not None:
        consulta = consulta.exclude(pk=excluir)
    return consulta.aggregate(m=Max('ultimo_usado'))['m']


def _bloquear_puntos(*ids) -> dict:
    """Bloquea los puntos en orden de id. Todas las escrituras de numeración bloquean primero el punto y
    después sus rangos (mismo orden en todas partes: sin bloqueos cruzados en PostgreSQL)."""
    return {p.pk: p for p in PuntoExpedicion.objects.select_for_update().filter(pk__in=set(ids)).order_by('pk')}


def crear_rango(*, institucion, datos: dict, request=None) -> RangoNumeracion:
    datos = dict(datos)
    code = code_valido(datos.pop('Code', ''))
    validar_misma_institucion(institucion, datos['punto'])
    with transaction.atomic():
        # Bloquea el punto: dos rangos cargados a la vez no pueden superponerse sin verse.
        punto = _bloquear_puntos(datos['punto'].pk)[datos['punto'].pk]
        if not punto.activo:
            raise ErrorNegocio('El punto de expedición está desactivado.')
        datos['punto'] = punto
        rango = RangoNumeracion(institucion=institucion, Code=code, **datos)
        _validar_rango(rango)
        _guardar(rango, f'Ya existe un rango con el código {code}.')
        registrar('rango_numeracion_creado', request=request, entidad='rango_numeracion', entidad_id=rango.Code,
                  despues=foto_rango(rango))
    return rango


# Una vez emitido un documento con el rango, estos campos quedan fijos.
FIJOS_EN_USO = ('punto', 'tipo_documento', 'timbrado', 'desde')


def actualizar_rango(rango: RangoNumeracion, datos: dict, *, request=None) -> RangoNumeracion:
    datos = dict(datos)
    datos.pop('Code', None)
    with transaction.atomic():
        actual = RangoNumeracion.objects.get(pk=rango.pk)
        nuevo_punto = datos.get('punto')
        if nuevo_punto is not None:
            validar_misma_institucion(actual.institucion, nuevo_punto)
        puntos = _bloquear_puntos(actual.punto_id, *([nuevo_punto.pk] if nuevo_punto is not None else []))
        if nuevo_punto is not None and nuevo_punto.pk != actual.punto_id:
            if not puntos[nuevo_punto.pk].activo:
                raise ErrorNegocio('El punto de expedición elegido está desactivado.')
            datos['punto'] = puntos[nuevo_punto.pk]
        rango = RangoNumeracion.objects.select_for_update().get(pk=rango.pk)
        if rango.en_uso:
            cambiados = [c for c in FIJOS_EN_USO if c in datos and datos[c] != getattr(rango, c)]
            if cambiados:
                raise ErrorNegocio('Este rango ya se usó: solo se puede ampliar «hasta», cambiar la vigencia, '
                                   'las observaciones o desactivarlo.')
        antes = foto_rango(rango)
        for campo, valor in datos.items():
            setattr(rango, campo, valor)
        _validar_rango(rango)
        rango.save()
        despues = foto_rango(rango)
        accion = 'rango_numeracion_modificado'
        if antes['activo'] != despues['activo']:
            accion = 'rango_numeracion_' + ('restaurado' if despues['activo'] else 'desactivado')
        registrar(accion, request=request, entidad='rango_numeracion', entidad_id=rango.Code, antes=antes,
                  despues=despues)
    return rango


# --- Asignación de SerNr -------------------------------------------------------------------------

def tomar_sernr(punto: PuntoExpedicion, tipo_documento: str, *, institucion, fecha=None) -> tuple[int, RangoNumeracion]:
    """
    Entrega el próximo `SerNr` para un documento de `tipo_documento` en `punto`, y el rango del que salió
    (de él se copia el timbrado al documento). `institucion` es la de la sesión (se verifica que el punto sea suyo). Debe llamarse dentro de la MISMA transacción que guarda el
    documento: si el documento no se guarda, el número no se consume.

    Usa los rangos activos y vigentes en `fecha`, en orden (vigencia y luego «desde»); cuando uno se
    agota sigue con el próximo. Sin numeración disponible, no se emite: el error lo explica.
    """
    if tipo_documento not in TipoDocumento.values:
        raise ErrorNegocio('Tipo de documento inválido.')
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError('tomar_sernr debe llamarse dentro de transaction.atomic().')
    validar_misma_institucion(institucion, punto)
    fecha = fecha or timezone.localdate()
    punto = _bloquear_puntos(punto.pk)[punto.pk]
    if not punto.activo:
        raise ErrorNegocio(f'El punto de expedición {punto.Code} está desactivado.')
    rangos = (RangoNumeracion.objects.select_for_update()
              .filter(institucion_id=punto.institucion_id, punto=punto, tipo_documento=tipo_documento, activo=True)
              .filter(Q(vigencia_desde__isnull=True) | Q(vigencia_desde__lte=fecha))
              .filter(Q(vigencia_hasta__isnull=True) | Q(vigencia_hasta__gte=fecha))
              # Sin fecha de inicio = el más antiguo (igual en SQLite y PostgreSQL).
              .order_by(F('vigencia_desde').asc(nulls_first=True), 'desde'))
    for rango in rangos:
        siguiente = rango.desde if rango.ultimo_usado is None else rango.ultimo_usado + 1
        tope = _mayor_emitido(punto.pk, tipo_documento, rango.timbrado, excluir=rango.pk)
        if tope is not None and siguiente <= tope:
            continue  # defensa: nunca entregar un número menor que uno ya emitido (la validación lo impide)
        if siguiente <= rango.hasta:
            rango.ultimo_usado = siguiente
            rango.save(update_fields=['ultimo_usado', 'actualizado_en'])
            return siguiente, rango
    raise ErrorNegocio(
        f'No hay numeración disponible para «{TipoDocumento(tipo_documento).label}» en el punto {punto.Code} '
        f'({punto.prefijo}) al {fecha:%d/%m/%Y}: cargue o active un rango de numeración.',
        codigo='sin_numeracion',
    )
