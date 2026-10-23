"""
Reglas de tarifas y liquidaciones. La liquidación se genera sola cuando una lectura queda confirmada (decisión
21/10/2026), dentro de la misma transacción; si no hay tarifa vigente, la lectura igual se confirma y queda «sin
liquidar» hasta que la oficina cargue la tarifa y la liquide.
"""
import secrets

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from apps.auditoria.servicios import registrar
from comun.codigos import code_valido
from comun.errores import ErrorNegocio
from comun.modelos import validar_misma_institucion

from .calculo import ErrorTarifa, calcular, concepto_a_dict, validar_conceptos
from .models import IMPORTE_MAXIMO, ConceptoTarifa, LineaLiquidacion, Liquidacion, Tarifa, VersionTarifa

ALFABETO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def foto_tarifa(t: Tarifa) -> dict:
    return {'Code': t.Code, 'nombre': t.nombre, 'por_defecto': t.por_defecto, 'activa': t.activa}


def _guardar(objeto, mensaje):
    try:
        with transaction.atomic():
            objeto.save()
    except IntegrityError:
        raise ErrorNegocio(mensaje)


# --- Tarifas (tipos de conexión) ------------------------------------------------------------------

def _bloquear_institucion(institucion):
    """Serializa los cambios de «tarifa por defecto» de una institución (nunca dos ni ninguna)."""
    from apps.plataforma.models import Institucion
    Institucion.objects.select_for_update().get(pk=institucion.pk)


def _unica_por_defecto(tarifa: Tarifa):
    if tarifa.por_defecto and not tarifa.activa:
        raise ErrorNegocio('La tarifa por defecto debe estar activa.')
    if tarifa.por_defecto:
        Tarifa.objects.de(tarifa.institucion).filter(por_defecto=True).exclude(pk=tarifa.pk).update(por_defecto=False)


def crear_tarifa(*, institucion, datos: dict, request=None) -> Tarifa:
    datos = dict(datos)
    code = code_valido(datos.pop('Code', ''))
    with transaction.atomic():
        _bloquear_institucion(institucion)
        tarifa = Tarifa(institucion=institucion, Code=code, **datos)
        if not Tarifa.objects.de(institucion).exists() and tarifa.activa:
            tarifa.por_defecto = True  # la primera es la de por defecto
        _unica_por_defecto(tarifa)
        _guardar(tarifa, f'Ya existe una tarifa con el código {code}.')
        registrar('tarifa_creada', request=request, entidad='tarifa', entidad_id=tarifa.Code, despues=foto_tarifa(tarifa))
    return tarifa


def actualizar_tarifa(tarifa: Tarifa, datos: dict, *, request=None) -> Tarifa:
    datos = dict(datos)
    datos.pop('Code', None)
    with transaction.atomic():
        _bloquear_institucion(tarifa.institucion)
        tarifa = Tarifa.objects.select_for_update().get(pk=tarifa.pk)
        antes = foto_tarifa(tarifa)
        if tarifa.por_defecto and datos.get('por_defecto') is False:
            raise ErrorNegocio('Marque otra tarifa como «por defecto» en lugar de desmarcar esta.')
        for campo, valor in datos.items():
            setattr(tarifa, campo, valor)
        if tarifa.por_defecto and not tarifa.activa:
            raise ErrorNegocio('La tarifa por defecto no se puede desactivar.')
        _unica_por_defecto(tarifa)
        _guardar(tarifa, 'No se pudo guardar la tarifa (otra persona la cambió al mismo tiempo): vuelva a intentar.')
        registrar('tarifa_modificada', request=request, entidad='tarifa', entidad_id=tarifa.Code, antes=antes,
                  despues=foto_tarifa(tarifa))
    return tarifa


# --- Versiones y conceptos -----------------------------------------------------------------------

def _validar(conceptos):
    try:
        validar_conceptos(conceptos)
    except ErrorTarifa as error:
        raise ErrorNegocio(str(error))
    if not conceptos:
        raise ErrorNegocio('La versión necesita al menos un concepto.')


# Datos que usa cada tipo: los demás se guardan vacíos (no ensucian la instantánea).
CAMPOS_POR_TIPO = {'minimo': {'cantidad', 'precio'}, 'excedente': {'precio'}, 'tramo': {'desde', 'hasta', 'precio'},
                   'por_m3': {'precio'}, 'fijo': {'precio'}, 'porcentaje': {'porcentaje'}}


def _crear_conceptos(version, conceptos):
    for n, c in enumerate(conceptos):
        usados = CAMPOS_POR_TIPO[c['tipo']]
        ConceptoTarifa.objects.create(
            institucion=version.institucion, version=version, orden=n, nombre=c['nombre'].strip(), tipo=c['tipo'],
            iva=c['iva'], **{campo: (c.get(campo) if campo in usados else None)
                             for campo in ('cantidad', 'desde', 'hasta', 'precio', 'porcentaje')})


def foto_version(v: VersionTarifa) -> dict:
    return {'tarifa': v.tarifa.Code, 'vigente_desde': v.vigente_desde,
            'conceptos': [concepto_a_dict(c) for c in v.conceptos.all()]}


def _exigir_sin_liquidaciones_desde(tarifa, periodo, *, salvo_version=None):
    """Una versión nueva (o un cambio) no puede alcanzar períodos ya liquidados con esta tarifa: no hay precios
    retroactivos (lo liquidado conserva sus valores y una reliquidación no cambiaría de precio)."""
    liquidaciones = Liquidacion.objects.filter(tarifa=tarifa)
    if salvo_version is not None:
        liquidaciones = liquidaciones.exclude(version=salvo_version)
    ultimo = liquidaciones.aggregate(m=Max('periodo'))['m']
    if ultimo and periodo <= ultimo:
        raise ErrorNegocio(f'Ya hay liquidaciones con esta tarifa hasta {ultimo}: la vigencia debe empezar después de ese período.')


def crear_version(tarifa: Tarifa, *, vigente_desde: str, conceptos: list[dict], observaciones='', request=None):
    _validar(conceptos)
    with transaction.atomic():
        tarifa = Tarifa.objects.select_for_update().get(pk=tarifa.pk)
        _exigir_sin_liquidaciones_desde(tarifa, vigente_desde)
        version = VersionTarifa(institucion=tarifa.institucion, tarifa=tarifa, vigente_desde=vigente_desde,
                                observaciones=observaciones)
        _guardar(version, f'La tarifa ya tiene una versión vigente desde {vigente_desde}: modifíquela o elija otro período.')
        _crear_conceptos(version, conceptos)
        registrar('tarifa_version_creada', request=request, entidad='tarifa', entidad_id=tarifa.Code,
                  despues=foto_version(version))
    return version


def actualizar_version(version: VersionTarifa, *, conceptos: list[dict] | None = None, observaciones=None, request=None):
    """Solo mientras ninguna liquidación la usó: después se crea una versión nueva (los históricos no cambian)."""
    with transaction.atomic():
        version = VersionTarifa.objects.select_for_update(of=('self',)).select_related('tarifa').get(pk=version.pk)
        if conceptos is not None:
            if version.liquidaciones.exists():
                raise ErrorNegocio('Esta versión ya se usó en liquidaciones: para cambiar precios cree una versión nueva '
                                   '(con vigencia desde el próximo período).')
            _exigir_sin_liquidaciones_desde(version.tarifa, version.vigente_desde, salvo_version=version)
            _validar(conceptos)
            antes = foto_version(version)
            version.conceptos.all().delete()
            _crear_conceptos(version, conceptos)
        else:
            antes = foto_version(version)
        if observaciones is not None:
            version.observaciones = observaciones
            version.save(update_fields=['observaciones', 'actualizado_en'])
        registrar('tarifa_version_modificada', request=request, entidad='tarifa', entidad_id=version.tarifa.Code,
                  antes=antes, despues=foto_version(version))
    return version


def version_vigente(tarifa: Tarifa, periodo: str) -> VersionTarifa | None:
    return tarifa.versiones.filter(vigente_desde__lte=periodo).order_by('-vigente_desde').first()


def tarifa_de(conexion) -> Tarifa | None:
    if conexion.tarifa_id:
        return conexion.tarifa
    return Tarifa.objects.de(conexion.institucion).filter(por_defecto=True).first()


def simular(tarifa: Tarifa, *, periodo: str, consumo) -> dict:
    version = version_vigente(tarifa, periodo)
    if version is None:
        raise ErrorNegocio(f'La tarifa {tarifa.Code} no tiene una versión vigente en {periodo}.')
    try:
        return {'version': version.vigente_desde,
                **calcular([concepto_a_dict(c) for c in version.conceptos.all()], consumo)}
    except ErrorTarifa as error:
        raise ErrorNegocio(str(error))


# --- Liquidaciones -------------------------------------------------------------------------------

def _nuevo_numero(institucion) -> str:
    for _ in range(20):
        numero = 'LQ-' + ''.join(secrets.choice(ALFABETO) for _ in range(8))
        if not Liquidacion.objects.filter(institucion=institucion, numero=numero).exists():
            return numero
    raise RuntimeError('No se pudo generar el número de liquidación.')


def foto_liquidacion(q: Liquidacion) -> dict:
    return {'numero': q.numero, 'lectura': q.lectura.comprobante, 'conexion': q.conexion.Code, 'periodo': q.periodo,
            'tarifa': q.tarifa.Code, 'version': q.version.vigente_desde, 'consumo': str(q.consumo), 'total': str(q.total),
            'estado': q.estado}


def liquidar(lectura, *, tarifa=None, request=None) -> Liquidacion | None:
    """
    Liquida una lectura CONFIRMADA con la tarifa de su conexión vigente en su período. Debe llamarse dentro de la
    transacción que confirma la lectura. Devuelve None si no hay tarifa o versión vigente (queda sin liquidar).
    """
    from apps.lecturas.models import Lectura
    if lectura.estado != Lectura.Estado.CONFIRMADA or lectura.consumo is None:
        raise ErrorNegocio('Solo se liquidan lecturas confirmadas.')
    if Liquidacion.objects.filter(lectura=lectura, estado=Liquidacion.Estado.VIGENTE).exists():
        raise ErrorNegocio('La lectura ya tiene una liquidación vigente.', codigo='ya_liquidada')
    # Al reliquidar una corrección se usa la tarifa de la liquidación anterior (la del período), no la actual.
    tarifa = tarifa or tarifa_de(lectura.conexion)
    version = version_vigente(tarifa, lectura.periodo) if tarifa else None
    if version is None:
        return None
    validar_misma_institucion(lectura.institucion, tarifa)
    # Bloquea la versión: nadie puede cambiar sus conceptos mientras se la usa (queda «usada» al confirmar).
    version = VersionTarifa.objects.select_for_update().get(pk=version.pk)
    parametros = [concepto_a_dict(c) for c in version.conceptos.all()]
    try:
        resultado = calcular(parametros, lectura.consumo)
    except ErrorTarifa:
        return None  # tarifa mal configurada: queda sin liquidar y la oficina lo ve
    importes = [resultado['total'], *(l['importe'] for l in resultado['lineas']), *(l['cantidad'] for l in resultado['lineas'])]
    if any(abs(v) >= IMPORTE_MAXIMO for v in importes):
        return None  # importe desmesurado (lectura mal tipeada): queda sin liquidar para revisar
    liquidacion = Liquidacion.objects.create(
        institucion=lectura.institucion, numero=_nuevo_numero(lectura.institucion), lectura=lectura,
        conexion=lectura.conexion, periodo=lectura.periodo, tarifa=tarifa, version=version, parametros=parametros,
        consumo=lectura.consumo, subtotal_exento=resultado['subtotal_exento'], subtotal_iva5=resultado['subtotal_iva5'],
        subtotal_iva10=resultado['subtotal_iva10'], iva5=resultado['iva5'], iva10=resultado['iva10'],
        total=resultado['total'])
    for linea in resultado['lineas']:
        LineaLiquidacion.objects.create(
            institucion=lectura.institucion, liquidacion=liquidacion, orden=linea['orden'], concepto=linea['concepto'],
            tipo=linea['tipo'], cantidad=linea['cantidad'], precio=linea['precio'], importe=linea['importe'],
            iva=linea['iva'])
    registrar('liquidacion_generada', request=request, entidad='liquidacion', entidad_id=liquidacion.numero,
              despues=foto_liquidacion(liquidacion))
    return liquidacion


def anular_vigente(lectura, *, motivo: str, usuario=None, request=None) -> Liquidacion | None:
    """Anula la liquidación vigente de una lectura (la lectura se corrigió, anuló o volvió a revisión)."""
    liquidacion = (Liquidacion.objects.select_for_update().filter(lectura=lectura, estado=Liquidacion.Estado.VIGENTE)
                   .first())
    if liquidacion is None:
        return None
    # Una liquidación ya facturada no se anula así: primero se anula la factura (o, más adelante, nota de crédito).
    factura = liquidacion.asignaciones.filter(estado='vigente').select_related('factura').first()
    if factura is not None:
        raise ErrorNegocio(f'La lectura ya está facturada (factura {factura.factura.numero_impreso}): anule primero la '
                           'factura para corregirla o anularla.', codigo='ya_facturada')
    liquidacion.estado = Liquidacion.Estado.ANULADA
    liquidacion.motivo_anulacion = motivo
    liquidacion.anulada_por = usuario
    liquidacion.anulada_en = timezone.now()
    liquidacion.save()
    registrar('liquidacion_anulada', request=request, entidad='liquidacion', entidad_id=liquidacion.numero,
              motivo=motivo, despues=foto_liquidacion(liquidacion))
    return liquidacion


def liquidar_pendientes(institucion, *, periodo: str | None = None, request=None) -> dict:
    """Liquida las lecturas confirmadas que quedaron sin liquidar (ej. se cargó la tarifa después)."""
    from apps.lecturas.models import Lectura
    pendientes = (Lectura.objects.de(institucion).filter(estado=Lectura.Estado.CONFIRMADA)
                  .exclude(liquidaciones__estado=Liquidacion.Estado.VIGENTE)
                  .select_related('conexion__tarifa', 'institucion'))
    if periodo:
        pendientes = pendientes.filter(periodo=periodo)
    liquidadas, sin_tarifa = [], []
    for lectura in pendientes:
        with transaction.atomic():
            lectura = Lectura.objects.select_for_update(of=('self',)).select_related('conexion__tarifa', 'institucion').get(pk=lectura.pk)
            if lectura.estado != Lectura.Estado.CONFIRMADA or lectura.liquidaciones.filter(estado='vigente').exists():
                continue
            resultado = liquidar(lectura, request=request)
            (liquidadas if resultado else sin_tarifa).append(lectura.comprobante)
    return {'liquidadas': liquidadas, 'sin_tarifa': sin_tarifa}
