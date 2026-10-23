"""
Reglas de caja y gastos (Fase 7). Las vistas no tocan saldos ni movimientos.

Consistencia (sección 18): cobrar, gastar y cerrar bloquean la fila de la sesión (`select_for_update`): un cobro nunca
entra a una sesión que se está cerrando, y lo esperado del cierre se calcula con la sesión bloqueada.
Una sesión cerrada no recibe movimientos: las reversiones posteriores van a la caja abierta de quien revierte, con
referencia al movimiento original (nunca se modifica ni se borra el original).
"""
import secrets
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.auditoria.servicios import registrar
from apps.cobranzas.models import FormaPago
from apps.plataforma.models import siguiente_numero
from comun import archivos_privados
from comun.errores import ErrorNegocio
from comun.modelos import validar_misma_institucion

from .models import (CATEGORIAS_INICIALES, AdjuntoGasto, BoletaGasto, Caja, CategoriaGasto, DeclaracionCierre, Gasto,
                     MovimientoCaja, SesionCaja)

CERO = Decimal('0')
ALFABETO = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
E = SesionCaja.Estado
M = MovimientoCaja


def _referencia(modelo, institucion, prefijo: str) -> str:
    for _ in range(20):
        ref = prefijo + ''.join(secrets.choice(ALFABETO) for _ in range(8))
        if not modelo.objects.filter(institucion=institucion, referencia=ref).exists():
            return ref
    raise RuntimeError('No se pudo generar la referencia.')


def _importe(valor, *, permitir_cero=False) -> Decimal:
    try:
        importe = Decimal(str(valor))
    except Exception:
        raise ErrorNegocio('Importe inválido.')
    if importe != importe.to_integral_value() or importe < 0 or (importe == 0 and not permitir_cero):
        raise ErrorNegocio('El importe debe ser un número entero de guaraníes' +
                           (' (cero o más).' if permitir_cero else ' mayor que cero.'))
    return importe


def crear_datos_iniciales(institucion) -> None:
    Caja.objects.get_or_create(institucion=institucion, Code='CAJA1', defaults={'nombre': 'Caja principal'})
    for code, nombre in CATEGORIAS_INICIALES:
        CategoriaGasto.objects.get_or_create(institucion=institucion, Code=code, defaults={'nombre': nombre})


# --- Sesiones -----------------------------------------------------------------------------------------

def sesion_abierta_de(usuario):
    return (SesionCaja.objects.filter(responsable=usuario, estado=E.ABIERTA).select_related('caja').first()
            if getattr(usuario, 'pk', None) else None)


def exigir_sesion(usuario) -> SesionCaja:
    """La sesión ABIERTA de quien cobra o paga, bloqueada hasta el fin de la transacción. Sin caja abierta no se
    cobra (decisión del cliente)."""
    sesion = (SesionCaja.objects.select_for_update().filter(responsable=usuario, estado=E.ABIERTA).first()
              if getattr(usuario, 'pk', None) else None)
    if sesion is None:
        raise ErrorNegocio('Abra su caja antes de cobrar o pagar (menú Caja → Mi caja).', codigo='caja_cerrada')
    return sesion


def abrir_sesion(*, institucion, caja: Caja, usuario, saldo_inicial, request=None) -> SesionCaja:
    validar_misma_institucion(institucion, caja)
    saldo_inicial = _importe(saldo_inicial, permitir_cero=True)
    if not caja.activa:
        raise ErrorNegocio(f'La caja {caja.Code} está desactivada.')
    efectivo = forma_efectivo(institucion)
    if efectivo is None and saldo_inicial > 0:
        raise ErrorNegocio('No hay una forma de pago de tipo efectivo donde contar el saldo inicial.')
    try:
        with transaction.atomic():
            sesion = _abrir(institucion, caja, usuario, saldo_inicial, efectivo, request)
    except IntegrityError:
        # Dos aperturas simultáneas (ej. dos pestañas): la base garantiza una sola; la otra recibe el aviso.
        raise ErrorNegocio('Ya tiene una caja abierta, o la caja acaba de ser abierta por otro cajero.',
                           codigo='ya_abierta')
    return sesion


def _abrir(institucion, caja, usuario, saldo_inicial, efectivo, request):
    """Se llama dentro de la transacción de `abrir_sesion`."""
    Caja.objects.select_for_update().get(pk=caja.pk)
    if SesionCaja.objects.filter(responsable=usuario, estado=E.ABIERTA).exists():
        raise ErrorNegocio('Ya tiene una caja abierta: ciérrela antes de abrir otra.', codigo='ya_abierta')
    otra = SesionCaja.objects.filter(caja=caja, estado=E.ABIERTA).select_related('responsable').first()
    if otra is not None:
        raise ErrorNegocio(f'La caja {caja.Code} ya está abierta por {otra.responsable.nombre_usuario}.',
                           codigo='caja_ocupada')
    sesion = SesionCaja.objects.create(
        institucion=institucion, referencia=_referencia(SesionCaja, institucion, 'S-'), caja=caja,
        responsable=usuario, abierta_en=timezone.now(), saldo_inicial=saldo_inicial, forma_inicial=efectivo)
    registrar('caja_abierta', request=request, usuario=usuario, institucion=institucion, entidad='sesion_caja',
              entidad_id=sesion.referencia, despues={'caja': caja.Code, 'saldo_inicial': str(saldo_inicial)})
    return sesion


def forma_efectivo(institucion):
    """La forma de pago donde se cuenta el saldo inicial: la primera de tipo efectivo."""
    return (FormaPago.objects.de(institucion).filter(tipo=FormaPago.Tipo.EFECTIVO)
            .order_by('-activa', 'orden', 'pk').first())


def resumen(sesion: SesionCaja) -> list[dict]:
    """Saldos SEPARADOS por forma de pago (efectivo, transferencias y POS no se suman como dinero en caja)."""
    efectivo = sesion.forma_inicial
    filas = {}
    for fila in (sesion.movimientos.values('forma_pago', 'tipo').annotate(total=Sum('importe')).order_by()):
        datos = filas.setdefault(fila['forma_pago'], {'ingresos': CERO, 'egresos': CERO})
        datos['ingresos' if fila['tipo'] == M.Tipo.INGRESO else 'egresos'] += fila['total']
    if efectivo is not None:
        filas.setdefault(efectivo.pk, {'ingresos': CERO, 'egresos': CERO})
    formas = {f.pk: f for f in FormaPago.objects.filter(pk__in=filas)}
    salida = []
    for pk, datos in filas.items():
        forma = formas[pk]
        inicial = sesion.saldo_inicial if efectivo is not None and pk == efectivo.pk else CERO
        salida.append({'forma_pago': forma.Code, 'nombre': forma.nombre, 'tipo': forma.tipo, 'saldo_inicial': inicial,
                       'ingresos': datos['ingresos'], 'egresos': datos['egresos'],
                       'esperado': inicial + datos['ingresos'] - datos['egresos'], 'orden': (forma.orden, forma.nombre)})
    salida.sort(key=lambda d: d.pop('orden'))
    return salida


def cerrar_sesion(sesion: SesionCaja, *, declarados: dict, observaciones: str = '', usuario, puede_supervisar=False,
                  request=None) -> SesionCaja:
    """Cierra con lo CONTADO por forma de pago. Si algo no coincide con lo esperado queda «en revisión»."""
    with transaction.atomic():
        sesion = SesionCaja.objects.select_for_update().get(pk=sesion.pk)
        if sesion.estado != E.ABIERTA:
            raise ErrorNegocio('La sesión ya está cerrada.')
        if sesion.responsable_id != usuario.pk and not puede_supervisar:
            raise ErrorNegocio('Solo el responsable (o un supervisor) cierra esta caja.')
        filas = {f['forma_pago']: f for f in resumen(sesion)}
        declarados = {k.strip().upper(): _importe(v, permitir_cero=True) for k, v in (declarados or {}).items()}
        # Una forma sin movimientos solo se puede declarar en cero (si no, la diferencia no figuraría en el arqueo).
        fuera = [k for k, v in declarados.items() if k not in filas and v != 0]
        if fuera:
            raise ErrorNegocio(f'No hubo movimientos en {", ".join(sorted(fuera))}: no puede declarar un importe ahí.',
                               codigo='forma_sin_movimientos')
        declarados = {k: v for k, v in declarados.items() if k in filas}
        desconocidas = set(declarados) - set(filas)
        formas = {f.Code: f for f in FormaPago.objects.de(sesion.institucion).filter(Code__in=set(filas) | desconocidas)}
        if desconocidas - set(formas):
            raise ErrorNegocio(f'Forma de pago desconocida: {", ".join(sorted(desconocidas - set(formas)))}.')
        faltan = [f['nombre'] for code, f in filas.items() if code not in declarados]
        if faltan:
            raise ErrorNegocio(f'Indique lo contado en: {", ".join(faltan)}.', codigo='falta_declarar')
        hay_diferencia = False
        for code, declarado in declarados.items():
            esperado = filas[code]['esperado'] if code in filas else CERO
            diferencia = declarado - esperado
            hay_diferencia = hay_diferencia or diferencia != 0
            DeclaracionCierre.objects.create(institucion=sesion.institucion, sesion=sesion, forma_pago=formas[code],
                                             esperado=esperado, declarado=declarado, diferencia=diferencia)
        sesion.estado = E.EN_REVISION if hay_diferencia else E.CERRADA
        sesion.cerrada_en = timezone.now()
        sesion.observaciones_cierre = (observaciones or '').strip()
        if hay_diferencia and not sesion.observaciones_cierre:
            raise ErrorNegocio('Hay diferencias entre lo contado y lo esperado: explíquelas en las observaciones.',
                               codigo='explicar_diferencia')
        sesion.save()
        registrar('caja_cerrada', request=request, usuario=usuario, institucion=sesion.institucion,
                  entidad='sesion_caja', entidad_id=sesion.referencia, motivo=sesion.observaciones_cierre,
                  despues={'estado': sesion.estado, 'declarado': {k: str(v) for k, v in declarados.items()}})
    return sesion


def revisar_sesion(sesion: SesionCaja, *, comentario: str, usuario, request=None) -> SesionCaja:
    comentario = (comentario or '').strip()
    if not comentario:
        raise ErrorNegocio('Escriba el resultado de la revisión.')
    with transaction.atomic():
        sesion = SesionCaja.objects.select_for_update().get(pk=sesion.pk)
        if sesion.estado != E.EN_REVISION:
            raise ErrorNegocio('Solo se revisan sesiones cerradas con diferencias.')
        sesion.estado = E.CERRADA
        ahora = timezone.now()
        sesion.revisada_por, sesion.revisada_en = usuario, ahora
        # Se agrega al historial de revisiones (nunca se pisa una revisión anterior).
        linea = f'{timezone.localtime(ahora):%d/%m/%Y %H:%M} {usuario.nombre_usuario}: {comentario}'
        sesion.comentario_revision = f'{sesion.comentario_revision}\n{linea}' if sesion.comentario_revision else linea
        sesion.save()
        registrar('caja_revisada', request=request, usuario=usuario, institucion=sesion.institucion,
                  entidad='sesion_caja', entidad_id=sesion.referencia, motivo=comentario)
    return sesion


# --- Movimientos de cobros (los llama apps.cobranzas dentro de SU transacción) ------------------------------

def registrar_cobro(pago, sesion: SesionCaja) -> MovimientoCaja:
    recibo = getattr(pago, 'recibo', None)
    descripcion = (f'Recibo {recibo.numero_impreso}' if recibo else 'Factura contado') + f' · {pago.cliente.nombre}'
    return MovimientoCaja.objects.create(
        institucion=pago.institucion, sesion=sesion, tipo=M.Tipo.INGRESO, origen=M.Origen.COBRO,
        forma_pago=pago.forma_pago, importe=pago.importe, descripcion=descripcion[:200], pago=pago,
        usuario=pago.usuario, fecha_hora=pago.fecha_hora)


def _sesion_para_reversion(original: MovimientoCaja, usuario) -> SesionCaja:
    """La reversión va a la sesión original si sigue abierta; si no, a la caja abierta de quien revierte (la sesión
    cerrada no se toca). Sin usuario (ej. rechazo automático del proveedor) y con la original cerrada, va igual a la
    original pero la deja EN REVISIÓN: el cambio queda a la vista, nunca en silencio."""
    sesion = SesionCaja.objects.select_for_update().get(pk=original.sesion_id)
    if sesion.estado == E.ABIERTA:
        return sesion
    if getattr(usuario, 'pk', None):
        abierta = SesionCaja.objects.select_for_update().filter(responsable=usuario, estado=E.ABIERTA).first()
        if abierta is None:
            raise ErrorNegocio('El movimiento original está en una caja ya cerrada: abra su caja para registrar la '
                               'devolución.', codigo='caja_cerrada')
        return abierta
    antes = sesion.estado
    nota = f'{timezone.localtime():%d/%m/%Y %H:%M} Reversión automática después del cierre: vuelve a revisión.'
    sesion.estado = E.EN_REVISION
    sesion.revisada_por, sesion.revisada_en = None, None
    sesion.comentario_revision = f'{sesion.comentario_revision}\n{nota}' if sesion.comentario_revision else nota
    sesion.save()
    registrar('caja_reabierta_a_revision', institucion=sesion.institucion, entidad='sesion_caja',
              entidad_id=sesion.referencia, motivo='Reversión automática de un movimiento después del cierre',
              antes={'estado': antes}, despues={'estado': sesion.estado, 'movimiento': original.descripcion})
    return sesion


def revertir_cobro(pago, *, usuario=None, motivo='') -> MovimientoCaja | None:
    original = MovimientoCaja.objects.filter(pago=pago, origen=M.Origen.COBRO).first()
    if original is None or hasattr(original, 'reversion'):
        return None  # pago anterior a la caja, o ya revertido
    sesion = _sesion_para_reversion(original, usuario)
    return MovimientoCaja.objects.create(
        institucion=pago.institucion, sesion=sesion, tipo=M.Tipo.EGRESO, origen=M.Origen.REVERSION_COBRO,
        forma_pago=original.forma_pago, importe=original.importe,
        descripcion=f'Reversión: {original.descripcion}'[:200], pago=pago, original=original,
        usuario=usuario if getattr(usuario, 'pk', None) else None, fecha_hora=timezone.now())


# --- Gastos ------------------------------------------------------------------------------------------

CAMPOS_BOLETA = ('fecha', 'importe', 'motivo', 'beneficiario', 'responsable')


def foto_gasto(g: Gasto) -> dict:
    return {'referencia': g.referencia, 'fecha': g.fecha.isoformat(), 'motivo': g.motivo, 'importe': str(g.importe),
            'categoria': g.categoria.Code, 'forma_pago': g.forma_pago.Code, 'comprobante': g.numero_comprobante,
            'beneficiario': g.beneficiario, 'responsable': g.responsable, 'estado': g.estado}


def _validar_gasto(institucion, datos: dict) -> dict:
    datos = dict(datos)
    validar_misma_institucion(institucion, datos.get('categoria'), datos.get('forma_pago'))
    if 'importe' in datos:
        datos['importe'] = _importe(datos['importe'])
    for campo in ('motivo', 'beneficiario'):
        if campo in datos and not (datos[campo] or '').strip():
            raise ErrorNegocio(f'Indique el {campo}.')
    if datos.get('categoria') is not None and not datos['categoria'].activa:
        raise ErrorNegocio('La categoría está desactivada.')
    if datos.get('forma_pago') is not None and not datos['forma_pago'].activa:
        raise ErrorNegocio('La forma de pago está desactivada.')
    return datos


def registrar_gasto(*, institucion, datos: dict, usuario, request=None) -> Gasto:
    datos = _validar_gasto(institucion, datos)
    with transaction.atomic():
        gasto = Gasto.objects.create(institucion=institucion, referencia=_referencia(Gasto, institucion, 'G-'),
                                     registrado_por=usuario, **datos)
        registrar('gasto_registrado', request=request, usuario=usuario, institucion=institucion, entidad='gasto',
                  entidad_id=gasto.referencia, despues=foto_gasto(gasto))
    return gasto


def editar_gasto(gasto: Gasto, datos: dict, *, usuario, request=None) -> Gasto:
    datos = _validar_gasto(gasto.institucion, datos)
    with transaction.atomic():
        gasto = Gasto.objects.select_for_update().get(pk=gasto.pk)
        if gasto.estado != Gasto.Estado.REGISTRADO:
            raise ErrorNegocio('Solo se modifica un gasto sin confirmar (uno confirmado se anula y se carga de nuevo).')
        if hasattr(gasto, 'boleta') and any(c in datos and datos[c] != getattr(gasto, c) for c in CAMPOS_BOLETA):
            raise ErrorNegocio('Ya se imprimió la boleta interna: la fecha, el importe, el motivo, el beneficiario y el '
                               'responsable no cambian (anule el gasto y cárguelo de nuevo).', codigo='tiene_boleta')
        antes = foto_gasto(gasto)
        for campo, valor in datos.items():
            setattr(gasto, campo, valor)
        gasto.save()
        registrar('gasto_modificado', request=request, usuario=usuario, institucion=gasto.institucion,
                  entidad='gasto', entidad_id=gasto.referencia, antes=antes, despues=foto_gasto(gasto))
    return gasto


def confirmar_gasto(gasto: Gasto, *, usuario, request=None) -> Gasto:
    """El gasto sale de la caja abierta de quien confirma. Repetir la confirmación no duplica el egreso."""
    with transaction.atomic():
        gasto = Gasto.objects.select_for_update().get(pk=gasto.pk)
        if gasto.estado == Gasto.Estado.CONFIRMADO:
            return gasto  # reintento: el egreso ya existe
        if gasto.estado != Gasto.Estado.REGISTRADO:
            raise ErrorNegocio('El gasto está anulado.')
        sesion = exigir_sesion(usuario)
        gasto.estado = Gasto.Estado.CONFIRMADO
        gasto.sesion = sesion
        gasto.confirmado_por, gasto.confirmado_en = usuario, timezone.now()
        gasto.save()
        MovimientoCaja.objects.create(
            institucion=gasto.institucion, sesion=sesion, tipo=M.Tipo.EGRESO, origen=M.Origen.GASTO,
            forma_pago=gasto.forma_pago, importe=gasto.importe, descripcion=f'Gasto: {gasto.motivo}'[:200],
            gasto=gasto, usuario=usuario, fecha_hora=gasto.confirmado_en)
        registrar('gasto_confirmado', request=request, usuario=usuario, institucion=gasto.institucion,
                  entidad='gasto', entidad_id=gasto.referencia, despues={**foto_gasto(gasto), 'sesion': sesion.referencia})
    return gasto


def anular_gasto(gasto: Gasto, *, motivo: str, usuario, request=None) -> Gasto:
    motivo = (motivo or '').strip()
    if not motivo:
        raise ErrorNegocio('Indique el motivo de la anulación.')
    with transaction.atomic():
        gasto = Gasto.objects.select_for_update().get(pk=gasto.pk)
        if gasto.estado == Gasto.Estado.ANULADO:
            raise ErrorNegocio('El gasto ya está anulado.')
        antes = foto_gasto(gasto)
        if gasto.estado == Gasto.Estado.CONFIRMADO:
            original = MovimientoCaja.objects.get(gasto=gasto, origen=M.Origen.GASTO)
            sesion = _sesion_para_reversion(original, usuario)
            MovimientoCaja.objects.create(
                institucion=gasto.institucion, sesion=sesion, tipo=M.Tipo.INGRESO, origen=M.Origen.REVERSION_GASTO,
                forma_pago=original.forma_pago, importe=original.importe,
                descripcion=f'Reversión: {original.descripcion}'[:200], gasto=gasto, original=original,
                usuario=usuario, fecha_hora=timezone.now())
        gasto.estado = Gasto.Estado.ANULADO
        gasto.anulado_por, gasto.anulado_en, gasto.motivo_anulacion = usuario, timezone.now(), motivo
        gasto.save()
        registrar('gasto_anulado', request=request, usuario=usuario, institucion=gasto.institucion, entidad='gasto',
                  entidad_id=gasto.referencia, motivo=motivo, antes=antes, despues=foto_gasto(gasto))
    return gasto


def adjuntar(gasto: Gasto, archivo, *, tipo: str, usuario, request=None) -> AdjuntoGasto:
    if tipo not in AdjuntoGasto.Tipo.values:
        raise ErrorNegocio('Tipo de adjunto inválido.')
    if gasto.estado == Gasto.Estado.ANULADO:
        raise ErrorNegocio('El gasto está anulado.')
    if tipo == AdjuntoGasto.Tipo.BOLETA_FIRMADA and not hasattr(gasto, 'boleta'):
        raise ErrorNegocio('Primero genere e imprima la boleta interna.')
    ruta = archivos_privados.guardar(gasto.institucion, 'gastos', archivo,
                                     permitidos=archivos_privados.IMAGENES + ('pdf',))
    adjunto = AdjuntoGasto.objects.create(institucion=gasto.institucion, gasto=gasto, tipo=tipo, archivo=ruta,
                                          subido_por=usuario)
    registrar('gasto_adjunto', request=request, usuario=usuario, institucion=gasto.institucion, entidad='gasto',
              entidad_id=gasto.referencia, tipo=tipo, archivo=ruta)
    return adjunto


def generar_boleta(gasto: Gasto, *, usuario, request=None) -> BoletaGasto:
    """Una boleta por gasto (número interno correlativo). Si ya existe, se devuelve la misma."""
    with transaction.atomic():
        gasto = Gasto.objects.select_for_update().get(pk=gasto.pk)
        existente = BoletaGasto.objects.filter(gasto=gasto).first()
        if existente is not None:
            return existente
        if gasto.estado == Gasto.Estado.ANULADO:
            raise ErrorNegocio('El gasto está anulado.')
        boleta = BoletaGasto.objects.create(
            institucion=gasto.institucion, gasto=gasto, numero=siguiente_numero(gasto.institucion, 'boleta_gasto'),
            **{c: getattr(gasto, c) for c in CAMPOS_BOLETA})
        registrar('boleta_gasto_generada', request=request, usuario=usuario, institucion=gasto.institucion,
                  entidad='gasto', entidad_id=gasto.referencia, boleta=boleta.numero_impreso)
    return boleta
