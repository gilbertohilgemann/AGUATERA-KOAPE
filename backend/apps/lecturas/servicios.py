"""
Reglas de las lecturas (sección 9 y 10). El servidor es la fuente oficial: recalcula la lectura anterior y el
consumo al recibir cada lectura, aunque el teléfono haya mostrado otros valores sin conexión.
"""
import secrets
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.auditoria.servicios import registrar
from apps.padron.models import InstalacionMedidor, Medidor, normalizar_numero_medidor
from apps.recorridos.models import Recorrido
from apps.recorridos.servicios import asignacion_de
from comun import archivos_privados
from comun.codigos import normalizar_code
from comun.errores import ErrorNegocio
from comun.geo import distancia_metros, validar_coordenadas

from .models import FotoLectura, Lectura

E = Lectura.Estado
M = Lectura.MotivoRevision
ALFABETO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # sin 0/O ni 1/I: se dicta sin confusiones
MAX_FOTOS_ADICIONALES = 3


def _nuevo_comprobante(institucion) -> str:
    for _ in range(20):
        codigo = 'L-' + ''.join(secrets.choice(ALFABETO) for _ in range(8))
        if not Lectura.objects.filter(institucion=institucion, comprobante=codigo).exists():
            return codigo
    raise RuntimeError('No se pudo generar un código de comprobante.')


def foto_lectura(l: Lectura) -> dict:
    return {'comprobante': l.comprobante, 'conexion': l.conexion.Code, 'medidor': l.medidor.Code, 'periodo': l.periodo,
            'lectura_anterior': str(l.lectura_anterior), 'lectura_actual': str(l.lectura_actual),
            'consumo': str(l.consumo) if l.consumo is not None else None, 'estado': l.estado,
            'motivo_revision': l.motivo_revision}


def lectura_anterior(instalacion: InstalacionMedidor, periodo: str):
    """
    (valor, fecha, origen): la última lectura CONFIRMADA de la misma instalación en un período anterior; si no
    hay, la lectura inicial de la instalación. Así un medidor nuevo nunca arrastra lecturas del anterior.
    """
    previa = (Lectura.objects.filter(instalacion=instalacion, estado=E.CONFIRMADA, periodo__lt=periodo)
              .order_by('-periodo', '-capturada_en').first())
    if previa is not None:
        return previa.lectura_actual, timezone.localtime(previa.capturada_en).date(), Lectura.OrigenAnterior.LECTURA
    return instalacion.lectura_inicial, instalacion.fecha_instalacion, Lectura.OrigenAnterior.INSTALACION


def _instalacion_para(medidor: Medidor, momento):
    """Instalación del medidor: la vigente o, si se sustituyó después, la que estaba vigente al leer."""
    fecha = timezone.localtime(momento).date()
    vigente = medidor.instalaciones.filter(fecha_retiro__isnull=True).select_related('conexion').first()
    if vigente is not None and vigente.fecha_instalacion <= fecha:
        return vigente, False
    anterior = (medidor.instalaciones.filter(fecha_instalacion__lte=fecha, fecha_retiro__gte=fecha)
                .select_related('conexion').order_by('-fecha_instalacion').first())
    if anterior is None:
        raise ErrorNegocio(f'El medidor {medidor.Code} no estaba instalado en esa fecha.', codigo='medidor_sin_instalacion')
    return anterior, True


def registrar_lectura(*, institucion, usuario, datos: dict, foto, fotos_adicionales=(), request=None):
    """
    Recibe una lectura del celular. Devuelve (lectura, creada). Es idempotente por `id_operacion`: si el
    teléfono la reenvía (cortes de conexión), devuelve la misma sin duplicarla.
    Todo o nada: la lectura y sus fotos se guardan juntas (no queda una lectura sin su foto obligatoria).
    """
    id_operacion = datos['id_operacion']
    existente = Lectura.objects.filter(institucion=institucion, id_operacion=id_operacion).first()
    if existente is not None:
        if existente.cobrador_id != usuario.pk:
            raise ErrorNegocio('Esa operación pertenece a otro usuario.', codigo='operacion_ajena')
        return existente, False

    recorrido = Recorrido.objects.de(institucion).filter(Code=normalizar_code(datos['recorrido'])).first()
    if recorrido is None:
        raise ErrorNegocio('El recorrido no existe.', codigo='recorrido_inexistente')
    asignacion = asignacion_de(recorrido, usuario, solo_activa=False)
    if asignacion is None:
        # Nunca estuvo asignado: no puede leer conexiones de este recorrido (prueba obligatoria 2).
        raise ErrorNegocio('No está asignado a este recorrido.', codigo='fuera_de_asignacion')
    if recorrido.estado in (Recorrido.Estado.PLANIFICADO, Recorrido.Estado.ANULADO):
        raise ErrorNegocio('El recorrido no está abierto.', codigo='recorrido_no_abierto')

    # Se identifica por su código; si no, por el número grabado en el medidor.
    medidor = (Medidor.objects.de(institucion).filter(Code=normalizar_code(datos['medidor'])).first()
               or Medidor.objects.de(institucion).filter(numero=normalizar_numero_medidor(datos['medidor'])).first())
    if medidor is None:
        raise ErrorNegocio('No existe un medidor con ese código o número en la institución.',
                           codigo='medidor_inexistente')

    capturada_en = datos['capturada_en']
    # Lo que pudo pasar mientras el teléfono estaba sin conexión no se pierde: va a revisión (D27).
    observaciones = []
    if capturada_en > timezone.now() + timedelta(hours=1):
        observaciones.append(M.FECHA_DUDOSA)

    # GPS obligatorio (decisión 20/10/2026).
    if datos.get('latitud') is None or datos.get('longitud') is None:
        raise ErrorNegocio('La lectura necesita la ubicación GPS del teléfono.', codigo='sin_gps')
    validar_coordenadas(datos['latitud'], datos['longitud'])

    origen = datos.get('foto_origen') or Lectura.OrigenFoto.CAMARA
    if origen == Lectura.OrigenFoto.GALERIA and not institucion.lecturas_permite_galeria:
        observaciones.append(M.GALERIA_NO_PERMITIDA)
    if foto is None:
        raise ErrorNegocio('Falta la foto del medidor (obligatoria).', codigo='sin_foto')
    if len(fotos_adicionales) > MAX_FOTOS_ADICIONALES:
        raise ErrorNegocio(f'Hasta {MAX_FOTOS_ADICIONALES} fotos adicionales.')

    actual = Decimal(datos['lectura_actual'])
    if actual < 0:
        raise ErrorNegocio('La lectura no puede ser negativa.')
    if medidor.lectura_maxima is not None and actual > medidor.lectura_maxima:
        raise ErrorNegocio(f'La lectura supera la capacidad del medidor ({medidor.lectura_maxima}).')

    with transaction.atomic():
        # Bloqueo de la fila del medidor: dos envíos simultáneos de la misma lectura se ordenan.
        medidor = Medidor.objects.select_for_update().get(pk=medidor.pk)
        existente = Lectura.objects.filter(institucion=institucion, id_operacion=id_operacion).first()
        if existente is not None:
            if existente.cobrador_id != usuario.pk:
                raise ErrorNegocio('Esa operación pertenece a otro usuario.', codigo='operacion_ajena')
            return existente, False
        instalacion, cambiado = _instalacion_para(medidor, capturada_en)
        conexion = instalacion.conexion
        if not recorrido.paradas.filter(conexion=conexion).exists():
            # Se quitó del recorrido (o pasó a otro) mientras el teléfono estaba sin conexión.
            observaciones.append(M.FUERA_DEL_RECORRIDO)

        anterior, fecha_anterior, origen_anterior = lectura_anterior(instalacion, recorrido.periodo)
        motivo = ''
        if cambiado:
            motivo = M.MEDIDOR_CAMBIADO
        elif observaciones:
            motivo = observaciones[0]
        elif _hay_posteriores(instalacion, recorrido.periodo):
            motivo = M.POSTERIOR_EXISTENTE
        elif Lectura.objects.filter(instalacion=instalacion, periodo=recorrido.periodo, estado=E.CONFIRMADA).exists():
            motivo = M.DUPLICADA
        elif recorrido.estado == Recorrido.Estado.CERRADO:
            motivo = M.RECORRIDO_CERRADO
        elif not asignacion.activa:
            motivo = M.ASIGNACION_RETIRADA
        elif actual < anterior:
            motivo = M.LECTURA_MENOR

        distancia = None
        if conexion.tiene_ubicacion:
            distancia = distancia_metros(datos['latitud'], datos['longitud'], conexion.latitud, conexion.longitud)

        lectura = Lectura.objects.create(
            institucion=institucion, comprobante=_nuevo_comprobante(institucion), id_operacion=id_operacion,
            recorrido=recorrido, conexion=conexion, instalacion=instalacion, medidor=medidor, periodo=recorrido.periodo,
            lectura_anterior=anterior, fecha_lectura_anterior=fecha_anterior, origen_anterior=origen_anterior,
            lectura_actual=actual, consumo=None if motivo or actual < anterior else actual - anterior,
            capturada_en=capturada_en, cobrador=usuario, latitud=datos['latitud'], longitud=datos['longitud'],
            precision_metros=datos.get('precision_metros'), distancia_metros=distancia, foto_origen=origen,
            estado=E.REVISION if motivo else E.CONFIRMADA, motivo_revision=motivo,
            comentario=(datos.get('comentario') or '').strip(),
        )
        guardados = []
        try:
            for n, archivo in enumerate([foto, *fotos_adicionales]):
                ruta = archivos_privados.guardar(institucion, 'lecturas', archivo)
                guardados.append(ruta)
                FotoLectura.objects.create(institucion=institucion, lectura=lectura, principal=n == 0, orden=n,
                                           origen=origen if n == 0 else Lectura.OrigenFoto.CAMARA, archivo=ruta)
        except Exception:
            # Todo o nada: si una foto no sirve, no quedan archivos sueltos de esta lectura.
            for ruta in guardados:
                try:
                    archivos_privados.ruta_absoluta(institucion, ruta).unlink()
                except Exception:  # noqa: BLE001
                    pass
            raise
        registrar('lectura_registrada', request=request, entidad='lectura', entidad_id=lectura.comprobante,
                  despues=foto_lectura(lectura), id_operacion=str(id_operacion))
        if lectura.estado == E.CONFIRMADA:
            _liquidar(lectura, request)  # decisión 21/10/2026: se liquida al confirmarse la lectura
    return lectura, True


def _liquidar(lectura, request, tarifa=None):
    from apps.tarifas.servicios import liquidar
    return liquidar(lectura, tarifa=tarifa, request=request)


def _anular_liquidacion(lectura, motivo, usuario, request):
    from apps.tarifas.servicios import anular_vigente
    return anular_vigente(lectura, motivo=motivo, usuario=usuario, request=request)


# --- Revisión en la oficina ---------------------------------------------------------------------------

def _bloquear(lectura) -> Lectura:
    """Bloquea primero el medidor (mismo orden que al registrar) y después la lectura."""
    Medidor.objects.select_for_update().get(pk=lectura.medidor_id)
    return Lectura.objects.select_for_update(of=('self',)).select_related('instalacion', 'conexion', 'medidor').get(pk=lectura.pk)


def _actualizar_anterior(lectura: Lectura) -> None:
    """Recalcula la lectura anterior al resolver: pudo cambiar (anulaciones, correcciones) desde que llegó."""
    valor, fecha, origen = lectura_anterior(lectura.instalacion, lectura.periodo)
    lectura.lectura_anterior, lectura.fecha_lectura_anterior, lectura.origen_anterior = valor, fecha, origen


def _motivo(motivo):
    motivo = (motivo or '').strip()
    if not motivo:
        raise ErrorNegocio('Indique el motivo (queda en la auditoría).')
    return motivo


def _hay_posteriores(instalacion, periodo, *, solo_confirmadas=False) -> bool:
    """Lecturas vigentes (confirmadas o en revisión) de la misma instalación en un período posterior."""
    consulta = Lectura.objects.filter(instalacion=instalacion, periodo__gt=periodo)
    if solo_confirmadas:
        return consulta.filter(estado=E.CONFIRMADA).exists()
    return consulta.exclude(estado=E.ANULADA).exists()


def autorizar(lectura: Lectura, *, consumo=None, motivo: str, usuario, request=None) -> Lectura:
    """
    Confirma una lectura que requería revisión. Si la lectura actual es menor que la anterior (vuelta a cero,
    cambio no registrado…) el consumo lo indica quien autoriza: el sistema no inventa consumos negativos.
    """
    motivo = _motivo(motivo)
    with transaction.atomic():
        lectura = _bloquear(lectura)
        if lectura.estado != E.REVISION:
            raise ErrorNegocio('Solo se autorizan lecturas que requieren revisión.')
        if _hay_posteriores(lectura.instalacion, lectura.periodo, solo_confirmadas=True):
            raise ErrorNegocio('Ya hay lecturas confirmadas de períodos posteriores de este medidor: confirmar esta cambiaría '
                               'sus consumos. Anule esta lectura o resuelva primero las posteriores.')
        _actualizar_anterior(lectura)
        otra = Lectura.objects.filter(instalacion=lectura.instalacion, periodo=lectura.periodo,
                                      estado=E.CONFIRMADA).exclude(pk=lectura.pk).first()
        if otra is not None:
            raise ErrorNegocio(f'Ya hay una lectura confirmada en el período ({otra.comprobante}): anúlela primero '
                               'o anule esta.')
        diferencia = lectura.lectura_actual - lectura.lectura_anterior
        if consumo is None:
            if diferencia < 0:
                raise ErrorNegocio('La lectura es menor que la anterior: indique el consumo a registrar.',
                                   codigo='consumo_requerido')
            consumo = diferencia
        consumo = Decimal(consumo)
        if consumo < 0:
            raise ErrorNegocio('El consumo no puede ser negativo.')
        antes = foto_lectura(lectura)
        lectura.estado, lectura.consumo = E.CONFIRMADA, consumo
        lectura.resuelta_por, lectura.resuelta_en, lectura.resolucion = usuario, timezone.now(), motivo
        lectura.save()
        registrar('lectura_autorizada', request=request, entidad='lectura', entidad_id=lectura.comprobante,
                  motivo=motivo, antes=antes, despues=foto_lectura(lectura))
        _liquidar(lectura, request)
    return lectura


def corregir(lectura: Lectura, *, lectura_actual, motivo: str, usuario, request=None) -> Lectura:
    """Corrige el valor leído (ej. error de tipeo visto en la foto). Recalcula el consumo; si queda menor que la
    anterior, pasa a revisión. No se corrige si ya hay lecturas posteriores (cambiaría su lectura anterior)."""
    motivo = _motivo(motivo)
    with transaction.atomic():
        lectura = _bloquear(lectura)
        if lectura.estado == E.ANULADA:
            raise ErrorNegocio('La lectura está anulada.')
        if _hay_posteriores(lectura.instalacion, lectura.periodo):
            raise ErrorNegocio('Ya hay lecturas posteriores de este medidor: no se puede corregir.')
        _actualizar_anterior(lectura)
        nueva = Decimal(lectura_actual)
        if nueva < 0:
            raise ErrorNegocio('La lectura no puede ser negativa.')
        if lectura.medidor.lectura_maxima is not None and nueva > lectura.medidor.lectura_maxima:
            raise ErrorNegocio('La lectura supera la capacidad del medidor.')
        antes = foto_lectura(lectura)
        lectura.lectura_actual = nueva
        if nueva < lectura.lectura_anterior:
            if lectura.estado != E.REVISION:  # si ya estaba en revisión, conserva el motivo original
                lectura.motivo_revision = M.LECTURA_MENOR
            lectura.estado, lectura.consumo = E.REVISION, None
        elif lectura.estado == E.CONFIRMADA:
            lectura.consumo = nueva - lectura.lectura_anterior
        lectura.resuelta_por, lectura.resuelta_en, lectura.resolucion = usuario, timezone.now(), motivo
        lectura.save()
        registrar('lectura_corregida', request=request, entidad='lectura', entidad_id=lectura.comprobante,
                  motivo=motivo, antes=antes, despues=foto_lectura(lectura))
        # La liquidación anterior queda anulada en el historial; si la lectura sigue confirmada, se liquida de nuevo.
        anterior = _anular_liquidacion(lectura, f'Lectura corregida: {motivo}', usuario, request)
        if lectura.estado == E.CONFIRMADA:
            _liquidar(lectura, request, tarifa=anterior.tarifa if anterior else None)
    return lectura


def anular(lectura: Lectura, *, motivo: str, usuario, request=None) -> Lectura:
    motivo = _motivo(motivo)
    with transaction.atomic():
        lectura = _bloquear(lectura)
        if lectura.estado == E.ANULADA:
            raise ErrorNegocio('La lectura ya está anulada.')
        if lectura.estado == E.CONFIRMADA and _hay_posteriores(lectura.instalacion, lectura.periodo):
            raise ErrorNegocio('Ya hay lecturas posteriores de este medidor: no se puede anular (cambiaría sus consumos).')
        antes = foto_lectura(lectura)
        lectura.estado = E.ANULADA
        lectura.resuelta_por, lectura.resuelta_en, lectura.resolucion = usuario, timezone.now(), motivo
        lectura.save()
        registrar('lectura_anulada', request=request, entidad='lectura', entidad_id=lectura.comprobante,
                  motivo=motivo, antes=antes, despues=foto_lectura(lectura))
        _anular_liquidacion(lectura, f'Lectura anulada: {motivo}', usuario, request)
    return lectura
