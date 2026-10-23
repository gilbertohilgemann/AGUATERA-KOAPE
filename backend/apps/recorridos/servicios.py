"""
Reglas de los recorridos: armado (por zona, barrio o selección), orden de visita, cobradores asignados,
estados y avance. Todo auditado; lo que tiene lecturas no se quita.
"""
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from apps.auditoria.servicios import registrar
from apps.identidad.permisos import permisos_efectivos
from apps.padron.models import Conexion, InstalacionMedidor
from comun.codigos import code_valido
from comun.errores import ErrorNegocio
from comun.modelos import validar_misma_institucion

from .models import AsignacionRecorrido, ConexionRecorrido, Recorrido

E = Recorrido.Estado
TRANSICIONES = {
    E.PLANIFICADO: {E.ABIERTO, E.ANULADO},
    E.ABIERTO: {E.CERRADO},
    E.CERRADO: {E.ABIERTO},  # reapertura: con motivo y auditada
    E.ANULADO: set(),
}
EDITABLES = {E.PLANIFICADO, E.ABIERTO}
# Conexiones que se pueden leer: las que están en servicio (con o sin suspensión) y tienen ubicación o no.
ESTADOS_LEIBLES = {Conexion.Estado.ACTIVA, Conexion.Estado.SUSPENDIDA, Conexion.Estado.PENDIENTE_UBICACION,
                   Conexion.Estado.EN_INSTALACION}


def foto_recorrido(r: Recorrido) -> dict:
    return {'Code': r.Code, 'nombre': r.nombre, 'periodo': r.periodo, 'estado': r.estado,
            'fecha_desde': r.fecha_desde.isoformat() if r.fecha_desde else None,
            'fecha_hasta': r.fecha_hasta.isoformat() if r.fecha_hasta else None}


def _bloquear(recorrido) -> Recorrido:
    return Recorrido.objects.select_for_update().get(pk=recorrido.pk)


def _exigir_editable(recorrido):
    if recorrido.estado not in EDITABLES:
        raise ErrorNegocio(f'El recorrido está «{recorrido.get_estado_display()}»: no se puede modificar.')


def crear_recorrido(*, institucion, datos: dict, request=None) -> Recorrido:
    datos = dict(datos)
    code = code_valido(datos.pop('Code', ''))
    datos.pop('estado', None)
    with transaction.atomic():
        recorrido = Recorrido(institucion=institucion, Code=code, **datos)
        try:
            with transaction.atomic():
                recorrido.save()
        except IntegrityError:
            raise ErrorNegocio(f'Ya existe un recorrido con el código {code}.')
        registrar('recorrido_creado', request=request, entidad='recorrido', entidad_id=recorrido.Code,
                  despues=foto_recorrido(recorrido))
    return recorrido


def actualizar_recorrido(recorrido: Recorrido, datos: dict, *, request=None) -> Recorrido:
    datos = dict(datos)
    datos.pop('Code', None)
    datos.pop('estado', None)
    with transaction.atomic():
        recorrido = _bloquear(recorrido)
        if 'periodo' in datos and datos['periodo'] != recorrido.periodo:
            raise ErrorNegocio('El período no se cambia: cree otro recorrido.')
        if recorrido.estado == E.ANULADO:
            raise ErrorNegocio('El recorrido está anulado.')
        antes = foto_recorrido(recorrido)
        for campo, valor in datos.items():
            setattr(recorrido, campo, valor)
        recorrido.save()
        registrar('recorrido_modificado', request=request, entidad='recorrido', entidad_id=recorrido.Code,
                  antes=antes, despues=foto_recorrido(recorrido))
    return recorrido


def _con_lectura(recorrido, conexion_ids) -> set:
    from apps.lecturas.models import Lectura
    return set(Lectura.objects.filter(recorrido=recorrido, conexion_id__in=conexion_ids)
               .exclude(estado=Lectura.Estado.ANULADA).values_list('conexion_id', flat=True))


def agregar_conexiones(recorrido: Recorrido, *, zona=None, barrio=None, conexiones=(), request=None) -> dict:
    """
    Suma conexiones al final del recorrido: las de una zona, un barrio o una selección. Solo las que están en
    servicio y tienen medidor vigente; las que ya están en otro recorrido del mismo período se informan y saltan.
    """
    with transaction.atomic():
        recorrido = _bloquear(recorrido)
        _exigir_editable(recorrido)
        validar_misma_institucion(recorrido.institucion, zona, barrio, *conexiones)
        candidatas = Conexion.objects.de(recorrido.institucion).filter(estado__in=ESTADOS_LEIBLES)
        if zona is not None:
            candidatas = candidatas.filter(barrio__zona=zona).order_by('barrio__nombre', 'direccion', 'Code')
        elif barrio is not None:
            candidatas = candidatas.filter(barrio=barrio).order_by('direccion', 'Code')
        elif conexiones:
            orden = {c.pk: n for n, c in enumerate(conexiones)}
            candidatas = sorted(candidatas.filter(pk__in=orden), key=lambda c: orden[c.pk])
        else:
            raise ErrorNegocio('Indique una zona, un barrio o las conexiones a agregar.')
        candidatas = list(candidatas)
        con_medidor = set(InstalacionMedidor.objects.filter(conexion__in=candidatas, fecha_retiro__isnull=True)
                          .values_list('conexion_id', flat=True))
        ocupadas = dict(ConexionRecorrido.objects.filter(conexion__in=candidatas, periodo=recorrido.periodo)
                        .values_list('conexion_id', 'recorrido__Code'))
        siguiente = (recorrido.paradas.aggregate(m=Max('orden'))['m'] or 0) + 1
        agregadas, sin_medidor, en_otro = [], [], []
        for conexion in candidatas:
            if conexion.pk in ocupadas:
                if ocupadas[conexion.pk] != recorrido.Code:
                    en_otro.append({'conexion': conexion.Code, 'recorrido': ocupadas[conexion.pk]})
                continue
            if conexion.pk not in con_medidor:
                sin_medidor.append(conexion.Code)
                continue
            try:
                with transaction.atomic():  # otro recorrido pudo tomarla en este mismo instante
                    ConexionRecorrido.objects.create(institucion=recorrido.institucion, recorrido=recorrido,
                                                     conexion=conexion, periodo=recorrido.periodo, orden=siguiente)
            except IntegrityError:
                en_otro.append({'conexion': conexion.Code, 'recorrido': '(otro)'})
                continue
            siguiente += 1
            agregadas.append(conexion.Code)
        if agregadas:
            registrar('recorrido_conexiones_agregadas', request=request, entidad='recorrido',
                      entidad_id=recorrido.Code, despues={'conexiones': agregadas})
    return {'agregadas': agregadas, 'sin_medidor': sin_medidor, 'en_otro_recorrido': en_otro}


def quitar_conexion(recorrido: Recorrido, conexion: Conexion, *, request=None) -> None:
    with transaction.atomic():
        recorrido = _bloquear(recorrido)
        _exigir_editable(recorrido)
        parada = recorrido.paradas.filter(conexion=conexion).first()
        if parada is None:
            raise ErrorNegocio('La conexión no está en el recorrido.')
        if _con_lectura(recorrido, [conexion.pk]):
            raise ErrorNegocio('La conexión ya tiene lectura en este recorrido: no se puede quitar.')
        parada.delete()  # es configuración del recorrido, no historia: queda en la auditoría
        registrar('recorrido_conexion_quitada', request=request, entidad='recorrido', entidad_id=recorrido.Code,
                  antes={'conexion': conexion.Code})


def ordenar(recorrido: Recorrido, codes: list[str], *, request=None) -> None:
    """Fija el orden de visita con la lista completa de códigos de conexión, en el orden deseado."""
    with transaction.atomic():
        recorrido = _bloquear(recorrido)
        _exigir_editable(recorrido)
        paradas = {p.conexion.Code: p for p in recorrido.paradas.select_related('conexion')}
        if sorted(codes) != sorted(paradas) or len(set(codes)) != len(codes):
            raise ErrorNegocio('Envíe todas las conexiones del recorrido, cada una una sola vez.')
        for n, code in enumerate(codes, start=1):
            parada = paradas[code]
            if parada.orden != n:
                parada.orden = n
                parada.save(update_fields=['orden', 'actualizado_en'])
        registrar('recorrido_ordenado', request=request, entidad='recorrido', entidad_id=recorrido.Code)


def puede_leer(usuario) -> bool:
    return usuario.is_active and 'lecturas.registrar' in permisos_efectivos(usuario)


def asignar_cobrador(recorrido: Recorrido, cobrador, *, request=None) -> AsignacionRecorrido:
    with transaction.atomic():
        recorrido = _bloquear(recorrido)
        _exigir_editable(recorrido)
        validar_misma_institucion(recorrido.institucion, cobrador)
        if not puede_leer(cobrador):
            raise ErrorNegocio(f'{cobrador.nombre_usuario} no tiene el permiso para tomar lecturas.')
        asignacion, creada = AsignacionRecorrido.objects.get_or_create(
            recorrido=recorrido, cobrador=cobrador, defaults={'institucion': recorrido.institucion})
        if not creada and asignacion.activa:
            raise ErrorNegocio('Ese cobrador ya está asignado.')
        asignacion.activa = True
        asignacion.save()
        registrar('recorrido_cobrador_asignado', request=request, entidad='recorrido', entidad_id=recorrido.Code,
                  despues={'cobrador': cobrador.nombre_usuario})
    return asignacion


def retirar_cobrador(recorrido: Recorrido, cobrador, *, request=None) -> None:
    with transaction.atomic():
        recorrido = _bloquear(recorrido)
        asignacion = recorrido.asignaciones.filter(cobrador=cobrador, activa=True).first()
        if asignacion is None:
            raise ErrorNegocio('Ese cobrador no está asignado.')
        asignacion.activa = False
        asignacion.save(update_fields=['activa', 'actualizado_en'])
        registrar('recorrido_cobrador_retirado', request=request, entidad='recorrido', entidad_id=recorrido.Code,
                  antes={'cobrador': cobrador.nombre_usuario})


def cambiar_estado(recorrido: Recorrido, nuevo: str, *, motivo: str = '', request=None) -> Recorrido:
    with transaction.atomic():
        recorrido = _bloquear(recorrido)
        if nuevo not in TRANSICIONES.get(recorrido.estado, set()):
            raise ErrorNegocio(f'No se puede pasar de «{recorrido.get_estado_display()}» a «{E(nuevo).label}».')
        motivo = (motivo or '').strip()
        if recorrido.estado == E.CERRADO and not motivo:
            raise ErrorNegocio('Indique el motivo de la reapertura.')
        if nuevo == E.ANULADO and not motivo:
            raise ErrorNegocio('Indique el motivo de la anulación.')
        if nuevo == E.ABIERTO and recorrido.estado == E.PLANIFICADO:
            if not recorrido.paradas.exists():
                raise ErrorNegocio('Agregue conexiones antes de abrir el recorrido.')
            if not recorrido.asignaciones.filter(activa=True).exists():
                raise ErrorNegocio('Asigne al menos un cobrador antes de abrir el recorrido.')
        anterior = recorrido.estado
        recorrido.estado = nuevo
        recorrido.save(update_fields=['estado', 'actualizado_en'])
        if nuevo == E.ANULADO:
            # Sin lecturas (solo se anula planificado): libera sus conexiones para otro recorrido del período.
            recorrido.paradas.all().delete()
        registrar('recorrido_estado', request=request, entidad='recorrido', entidad_id=recorrido.Code, motivo=motivo,
                  antes={'estado': anterior}, despues={'estado': nuevo})
    return recorrido


def avance(recorrido: Recorrido) -> dict:
    from apps.lecturas.models import Lectura
    total = recorrido.paradas.count()
    lecturas = Lectura.objects.filter(recorrido=recorrido).exclude(estado=Lectura.Estado.ANULADA)
    confirmadas = lecturas.filter(estado=Lectura.Estado.CONFIRMADA).values('conexion').distinct().count()
    revision = lecturas.filter(estado=Lectura.Estado.REVISION).values('conexion').distinct().count()
    leidas = lecturas.values('conexion').distinct().count()
    return {'total': total, 'leidas': leidas, 'confirmadas': confirmadas, 'en_revision': revision,
            'pendientes': max(total - leidas, 0)}


# --- Cobrador -----------------------------------------------------------------------------------------

def asignacion_de(recorrido: Recorrido, usuario, *, solo_activa=True) -> AsignacionRecorrido | None:
    consulta = recorrido.asignaciones.filter(cobrador=usuario)
    if solo_activa:
        consulta = consulta.filter(activa=True)
    return consulta.first()


def iniciar(recorrido: Recorrido, usuario, *, request=None) -> AsignacionRecorrido:
    with transaction.atomic():
        recorrido = _bloquear(recorrido)
        asignacion = asignacion_de(recorrido, usuario)
        if asignacion is None or recorrido.estado != E.ABIERTO:
            raise ErrorNegocio('El recorrido no está abierto para usted.')
        if asignacion.iniciado_en is None:
            asignacion.iniciado_en = timezone.now()
        asignacion.finalizado_en = None
        asignacion.save(update_fields=['iniciado_en', 'finalizado_en', 'actualizado_en'])
        registrar('recorrido_iniciado', request=request, entidad='recorrido', entidad_id=recorrido.Code)
    return asignacion


def finalizar(recorrido: Recorrido, usuario, *, request=None) -> AsignacionRecorrido:
    with transaction.atomic():
        recorrido = _bloquear(recorrido)
        asignacion = asignacion_de(recorrido, usuario)
        if asignacion is None:
            raise ErrorNegocio('No está asignado a este recorrido.')
        asignacion.finalizado_en = timezone.now()
        asignacion.save(update_fields=['finalizado_en', 'actualizado_en'])
        registrar('recorrido_finalizado', request=request, entidad='recorrido', entidad_id=recorrido.Code,
                  despues=avance(recorrido))
    return asignacion
