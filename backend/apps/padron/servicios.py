"""
Reglas del padrón. Las vistas validan formato y llaman a estas funciones; acá se verifican la
institución, los estados y las reglas, todo dentro de transacciones con bloqueo de filas.
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.auditoria.servicios import registrar
from comun.codigos import code_valido, normalizar_code
from comun.errores import ErrorNegocio
from comun.geo import validar_coordenadas
from comun.modelos import validar_misma_institucion

from .models import Cliente, Conexion, InstalacionMedidor, Medidor, TitularidadConexion, normalizar_numero_medidor

E = Conexion.Estado

# Transiciones válidas de estado de una conexión (sección 7.2). La suspensión nunca borra deudas ni historial.
TRANSICIONES = {
    E.EN_INSTALACION: {E.ACTIVA, E.PENDIENTE_UBICACION, E.ARCHIVADA},
    E.PENDIENTE_UBICACION: {E.ACTIVA, E.EN_INSTALACION, E.ARCHIVADA},
    E.ACTIVA: {E.SUSPENDIDA, E.DESCONECTADA, E.PENDIENTE_UBICACION},
    E.SUSPENDIDA: {E.ACTIVA, E.DESCONECTADA},
    E.DESCONECTADA: {E.ACTIVA, E.ARCHIVADA},
    E.ARCHIVADA: {E.DESCONECTADA},  # restauración: requiere motivo y queda auditada
}
# Estados en los que la conexión no admite instalar un medidor nuevo.
SIN_INSTALACION = {E.ARCHIVADA, E.DESCONECTADA}


def _hoy():
    return timezone.localdate()


def _code_obligatorio(datos: dict) -> str:
    """El `Code` de un maestro lo carga siempre el usuario (convención del proyecto)."""
    return code_valido(datos.pop('Code', ''))


def foto_cliente(c: Cliente) -> dict:
    return {'Code': c.Code, 'nombre': c.nombre, 'tipo_persona': c.tipo_persona, 'documento': c.documento,
            'telefono': c.telefono, 'correo': c.correo, 'direccion_referencia': c.direccion_referencia,
            'estado': c.estado}


def foto_conexion(c: Conexion) -> dict:
    return {'Code': c.Code, 'cliente': c.cliente.Code, 'direccion': c.direccion,
            'barrio': c.barrio.Code if c.barrio else None,
            'latitud': str(c.latitud) if c.latitud is not None else None,
            'longitud': str(c.longitud) if c.longitud is not None else None,
            'metodo_ubicacion': c.metodo_ubicacion, 'estado': c.estado,
            'tarifa': c.tarifa.Code if c.tarifa_id else None,
            'fecha_instalacion': c.fecha_instalacion.isoformat() if c.fecha_instalacion else None,
            'foto_vivienda': c.foto_vivienda}


def foto_medidor(m: Medidor) -> dict:
    return {'Code': m.Code, 'numero': m.numero, 'marca': m.marca, 'modelo': m.modelo, 'unidad': m.unidad,
            'lectura_maxima': str(m.lectura_maxima) if m.lectura_maxima is not None else None, 'estado': m.estado}


# --- Clientes ---------------------------------------------------------------------------------

def crear_cliente(*, institucion, datos: dict, request=None) -> Cliente:
    with transaction.atomic():
        code = _code_obligatorio(datos)
        cliente = Cliente(institucion=institucion, Code=code, **datos)
        cliente.fecha_alta = cliente.fecha_alta or _hoy()
        try:
            with transaction.atomic():
                cliente.save()
        except IntegrityError:
            raise ErrorNegocio(f'Ya existe un cliente con el código {code}.')
        registrar('cliente_creado', request=request, entidad='cliente', entidad_id=cliente.Code,
                  despues=foto_cliente(cliente))
    return cliente


def actualizar_cliente(cliente: Cliente, datos: dict, *, request=None) -> Cliente:
    with transaction.atomic():
        cliente = Cliente.objects.select_for_update().get(pk=cliente.pk)
        datos = dict(datos)
        if normalizar_code(datos.pop('Code', cliente.Code)) != cliente.Code:
            raise ErrorNegocio('El código no se cambia después del alta.')
        antes = foto_cliente(cliente)
        nuevo_estado = datos.get('estado', cliente.estado)
        if nuevo_estado == Cliente.Estado.ARCHIVADO and cliente.estado != Cliente.Estado.ARCHIVADO:
            vigentes = cliente.conexiones.exclude(estado=E.ARCHIVADA)
            if vigentes.exists():
                raise ErrorNegocio('No se puede archivar un cliente con conexiones que no están archivadas.',
                                   codigo='cliente_con_conexiones')
        for campo, valor in datos.items():
            setattr(cliente, campo, valor)
        cliente.save()
        despues = foto_cliente(cliente)
        accion = 'cliente_modificado'
        if antes['estado'] != despues['estado']:
            accion = 'cliente_archivado' if despues['estado'] == Cliente.Estado.ARCHIVADO else (
                'cliente_restaurado' if antes['estado'] == Cliente.Estado.ARCHIVADO else 'cliente_modificado')
        registrar(accion, request=request, entidad='cliente', entidad_id=cliente.Code, antes=antes, despues=despues)
    return cliente


# --- Conexiones -------------------------------------------------------------------------------

def _validar_barrio(institucion, barrio, anterior_id=None):
    if barrio is None:
        return
    validar_misma_institucion(institucion, barrio)
    if not barrio.activo and barrio.pk != anterior_id:
        raise ErrorNegocio('El barrio está archivado: elija otro.')


def _validar_ubicacion(datos: dict, conexion: Conexion | None = None, estado: str | None = None):
    """Coordenadas válidas y método coherente con ellas. Una conexión activa no puede quedar sin ubicación."""
    lat = datos.get('latitud', conexion.latitud if conexion else None)
    lon = datos.get('longitud', conexion.longitud if conexion else None)
    validar_coordenadas(lat, lon)
    if lat is None and lon is None:
        if (estado or (conexion.estado if conexion else None)) == E.ACTIVA:
            raise ErrorNegocio('Una conexión activa necesita ubicación. Si se desconoce, pásela a «Pendiente de ubicación».')
        datos['metodo_ubicacion'] = Conexion.MetodoUbicacion.SIN_UBICACION
        datos['precision_metros'] = None
    elif datos.get('metodo_ubicacion', conexion.metodo_ubicacion if conexion else None) in (
            None, Conexion.MetodoUbicacion.SIN_UBICACION):
        datos['metodo_ubicacion'] = Conexion.MetodoUbicacion.MANUAL


def crear_conexion(*, institucion, datos: dict, usuario=None, request=None) -> Conexion:
    cliente = datos['cliente']
    validar_misma_institucion(institucion, cliente)
    if cliente.estado == Cliente.Estado.ARCHIVADO:
        raise ErrorNegocio('El cliente está archivado: restáurelo antes de agregarle una conexión.')
    _validar_barrio(institucion, datos.get('barrio'))
    _validar_tarifa(institucion, datos.get('tarifa'))
    estado = datos.pop('estado', None) or E.EN_INSTALACION
    _validar_ubicacion(datos, estado=estado)
    if estado not in (E.EN_INSTALACION, E.PENDIENTE_UBICACION, E.ACTIVA):
        raise ErrorNegocio('Una conexión nueva solo puede estar en instalación, pendiente de ubicación o activa.')
    with transaction.atomic():
        code = _code_obligatorio(datos)
        conexion = Conexion(institucion=institucion, Code=code, estado=estado, **datos)
        try:
            with transaction.atomic():
                conexion.save()
        except IntegrityError:
            raise ErrorNegocio(f'Ya existe una conexión con el código {code}.')
        TitularidadConexion.objects.create(institucion=institucion, conexion=conexion, cliente=cliente,
                                           desde=conexion.fecha_instalacion or _hoy(), motivo='Alta de la conexión',
                                           registrado_por=usuario)
        registrar('conexion_creada', request=request, entidad='conexion', entidad_id=conexion.Code,
                  despues=foto_conexion(conexion))
    return conexion


CAMPOS_EDITABLES_CONEXION = {'direccion', 'barrio', 'latitud', 'longitud', 'metodo_ubicacion', 'precision_metros',
                             'fecha_instalacion', 'observaciones', 'tarifa'}


def _validar_tarifa(institucion, tarifa, anterior_id=None):
    if tarifa is None:
        return
    validar_misma_institucion(institucion, tarifa)
    if not tarifa.activa and tarifa.pk != anterior_id:
        raise ErrorNegocio('Esa tarifa está desactivada: elija otra.')


def actualizar_conexion(conexion: Conexion, datos: dict, *, request=None) -> Conexion:
    """Dirección, barrio, ubicación y observaciones. El estado y el titular tienen su propio procedimiento."""
    datos = dict(datos)
    if normalizar_code(datos.pop('Code', conexion.Code)) != conexion.Code:
        raise ErrorNegocio('El código no se cambia después del alta.')
    ajenos = set(datos) - CAMPOS_EDITABLES_CONEXION
    if ajenos:
        raise ErrorNegocio(f'Use el procedimiento correspondiente para cambiar: {", ".join(sorted(ajenos))}.')
    with transaction.atomic():
        conexion = Conexion.objects.select_for_update().get(pk=conexion.pk)
        if conexion.estado == E.ARCHIVADA:
            raise ErrorNegocio('La conexión está archivada: restáurela antes de modificarla.')
        if 'barrio' in datos:
            _validar_barrio(conexion.institucion, datos['barrio'], conexion.barrio_id)
        if 'tarifa' in datos:
            _validar_tarifa(conexion.institucion, datos['tarifa'], conexion.tarifa_id)
        if {'latitud', 'longitud', 'metodo_ubicacion'} & set(datos):
            _validar_ubicacion(datos, conexion)
        antes = foto_conexion(conexion)
        for campo, valor in datos.items():
            setattr(conexion, campo, valor)
        conexion.save()
        registrar('conexion_modificada', request=request, entidad='conexion', entidad_id=conexion.Code, antes=antes,
                  despues=foto_conexion(conexion))
    return conexion


def cambiar_estado_conexion(conexion: Conexion, nuevo: str, *, motivo: str, request=None) -> Conexion:
    motivo = (motivo or '').strip()
    if not motivo:
        raise ErrorNegocio('Indique el motivo del cambio de estado.')
    with transaction.atomic():
        conexion = Conexion.objects.select_for_update().get(pk=conexion.pk)
        if nuevo not in TRANSICIONES.get(conexion.estado, set()):
            raise ErrorNegocio(f'No se puede pasar de «{conexion.get_estado_display()}» a «{E(nuevo).label}».',
                               codigo='transicion_invalida')
        if nuevo == E.ACTIVA and not conexion.tiene_ubicacion:
            raise ErrorNegocio('Cargue la ubicación de la conexión antes de activarla.')
        if nuevo == E.ARCHIVADA and conexion.instalaciones.filter(fecha_retiro__isnull=True).exists():
            raise ErrorNegocio('Retire el medidor antes de archivar la conexión.', codigo='tiene_medidor')
        if conexion.estado == E.ARCHIVADA and conexion.cliente.estado == Cliente.Estado.ARCHIVADO:
            raise ErrorNegocio('El titular está archivado: restáurelo (o cambie el titular) antes de restaurar la conexión.')
        anterior = conexion.estado
        conexion.estado = nuevo
        conexion.save(update_fields=['estado', 'actualizado_en'])
        accion = 'conexion_restaurada' if anterior == E.ARCHIVADA else (
            'conexion_archivada' if nuevo == E.ARCHIVADA else 'conexion_estado')
        registrar(accion, request=request, entidad='conexion', entidad_id=conexion.Code, motivo=motivo,
                  antes={'estado': anterior}, despues={'estado': nuevo})
    return conexion


def cambiar_titular(conexion: Conexion, cliente: Cliente, *, desde, motivo: str, usuario=None, request=None) -> Conexion:
    motivo = (motivo or '').strip()
    if not motivo:
        raise ErrorNegocio('Indique el motivo del cambio de titular.')
    with transaction.atomic():
        conexion = Conexion.objects.select_for_update().get(pk=conexion.pk)
        validar_misma_institucion(conexion.institucion, cliente)
        if cliente.estado == Cliente.Estado.ARCHIVADO:
            raise ErrorNegocio('El cliente está archivado.')
        if cliente.pk == conexion.cliente_id:
            raise ErrorNegocio('Ese cliente ya es el titular de la conexión.')
        if desde > _hoy():
            raise ErrorNegocio('El cambio de titular no puede tener fecha futura.')
        if conexion.estado == E.ARCHIVADA:
            raise ErrorNegocio('La conexión está archivada.')
        vigente = conexion.titularidades.select_for_update().filter(hasta__isnull=True).first()
        if vigente is not None:
            if desde < vigente.desde:
                raise ErrorNegocio('La fecha del cambio no puede ser anterior al inicio del titular actual.')
            vigente.hasta = desde
            vigente.save(update_fields=['hasta', 'actualizado_en'])
        TitularidadConexion.objects.create(institucion=conexion.institucion, conexion=conexion, cliente=cliente,
                                           desde=desde, motivo=motivo, registrado_por=usuario)
        anterior = conexion.cliente.Code
        conexion.cliente = cliente
        conexion.save(update_fields=['cliente', 'actualizado_en'])
        registrar('conexion_titular', request=request, entidad='conexion', entidad_id=conexion.Code, motivo=motivo,
                  antes={'cliente': anterior}, despues={'cliente': cliente.Code, 'desde': desde.isoformat()})
    return conexion


def guardar_foto_vivienda(conexion: Conexion, archivo, *, request=None) -> Conexion:
    from comun import archivos_privados

    with transaction.atomic():
        conexion = Conexion.objects.select_for_update().get(pk=conexion.pk)
        if conexion.estado == E.ARCHIVADA:
            raise ErrorNegocio('La conexión está archivada.')
        ruta = archivos_privados.guardar(conexion.institucion, 'viviendas', archivo)
        anterior = conexion.foto_vivienda
        conexion.foto_vivienda = ruta
        conexion.save(update_fields=['foto_vivienda', 'actualizado_en'])
        registrar('conexion_foto_vivienda', request=request, entidad='conexion', entidad_id=conexion.Code,
                  antes={'foto_vivienda': anterior}, despues={'foto_vivienda': ruta})
    return conexion


# --- Medidores ----------------------------------------------------------------------------------

def _numero_libre(institucion, numero: str, *, excluir=None) -> str:
    """
    El número del medidor es único en la institución (si se cargó) y no puede ser el CÓDIGO de otro medidor: el
    cobrador identifica el medidor escribiendo uno u otro, y no debe haber dudas de cuál es.
    """
    numero = normalizar_numero_medidor(numero)
    if numero:
        otros = Medidor.objects.de(institucion).filter(Q(numero=numero) | Q(Code=numero))
        if excluir is not None:
            otros = otros.exclude(pk=excluir.pk)
        otro = otros.first()
        if otro is not None:
            raise ErrorNegocio(f'El número {numero} ya identifica al medidor {otro.Code}.', codigo='numero_repetido')
    return numero


def _code_libre_como_numero(institucion, code: str) -> None:
    otro = Medidor.objects.de(institucion).filter(numero=code).first()
    if otro is not None:
        raise ErrorNegocio(f'{code} ya es el número del medidor {otro.Code}: use otro código.', codigo='numero_repetido')


def crear_medidor(*, institucion, datos: dict, request=None) -> Medidor:
    datos['Code'] = _code_obligatorio(datos)
    _code_libre_como_numero(institucion, datos['Code'])
    datos['numero'] = _numero_libre(institucion, datos.get('numero', ''))
    if datos.get('estado') not in (None, Medidor.Estado.DISPONIBLE, Medidor.Estado.DANADO):
        raise ErrorNegocio('Un medidor nuevo queda disponible (o dañado). Se instala desde la conexión.')
    with transaction.atomic():
        medidor = Medidor(institucion=institucion, **datos)
        try:
            with transaction.atomic():
                medidor.save()
        except IntegrityError:
            raise ErrorNegocio(f'Ya existe un medidor con el código {datos["Code"]} o con el número {datos["numero"]}.')
        registrar('medidor_creado', request=request, entidad='medidor', entidad_id=medidor.Code,
                  despues=foto_medidor(medidor))
    return medidor


ESTADOS_MANUALES_MEDIDOR = {Medidor.Estado.DISPONIBLE, Medidor.Estado.DANADO, Medidor.Estado.BAJA, Medidor.Estado.RETIRADO}


def actualizar_medidor(medidor: Medidor, datos: dict, *, request=None) -> Medidor:
    with transaction.atomic():
        medidor = Medidor.objects.select_for_update().get(pk=medidor.pk)
        if normalizar_code(datos.pop('Code', medidor.Code)) != medidor.Code:
            raise ErrorNegocio('El código no se cambia después del alta.')
        if 'numero' in datos:
            datos['numero'] = _numero_libre(medidor.institucion, datos['numero'], excluir=medidor)
        if 'estado' in datos and datos['estado'] != medidor.estado:
            if medidor.estado == Medidor.Estado.INSTALADO or datos['estado'] not in ESTADOS_MANUALES_MEDIDOR:
                raise ErrorNegocio('Un medidor instalado cambia de estado al retirarlo desde su conexión.')
        maxima = datos.get('lectura_maxima', medidor.lectura_maxima)
        if maxima is not None and medidor.instalaciones.filter(lectura_inicial__gt=maxima).exists():
            raise ErrorNegocio('La lectura máxima no puede ser menor que una lectura inicial ya registrada.')
        antes = foto_medidor(medidor)
        for campo, valor in datos.items():
            setattr(medidor, campo, valor)
        try:
            with transaction.atomic():
                medidor.save()
        except IntegrityError:
            raise ErrorNegocio(f'El número {medidor.numero} ya es de otro medidor.', codigo='numero_repetido')
        registrar('medidor_modificado', request=request, entidad='medidor', entidad_id=medidor.Code, antes=antes,
                  despues=foto_medidor(medidor))
    return medidor


def _instalar(conexion: Conexion, medidor: Medidor, *, fecha, lectura_inicial: Decimal, usuario, observaciones=''):
    if medidor.estado not in (Medidor.Estado.DISPONIBLE, Medidor.Estado.RETIRADO):
        raise ErrorNegocio(f'El medidor {medidor.Code} está «{medidor.get_estado_display()}»: no se puede instalar.')
    if medidor.instalaciones.filter(fecha_retiro__isnull=True).exists():
        raise ErrorNegocio(f'El medidor {medidor.Code} ya está instalado en otra conexión.')
    if lectura_inicial < 0:
        raise ErrorNegocio('La lectura inicial no puede ser negativa.')
    if medidor.lectura_maxima is not None and lectura_inicial > medidor.lectura_maxima:
        raise ErrorNegocio('La lectura inicial supera la capacidad del medidor.')
    ultima = medidor.instalaciones.order_by('-fecha_retiro').first()
    if ultima is not None and ultima.fecha_retiro and fecha < ultima.fecha_retiro:
        raise ErrorNegocio('La fecha de instalación es anterior al último retiro de este medidor.')
    instalacion = InstalacionMedidor.objects.create(
        institucion=conexion.institucion, conexion=conexion, medidor=medidor, fecha_instalacion=fecha,
        lectura_inicial=lectura_inicial, instalado_por=usuario, observaciones=observaciones,
    )
    medidor.estado = Medidor.Estado.INSTALADO
    medidor.save(update_fields=['estado', 'actualizado_en'])
    return instalacion


def _retirar(instalacion: InstalacionMedidor, *, fecha, lectura_retiro: Decimal, motivo: str, usuario,
             estado_medidor: str, aceptar_lectura_menor: bool):
    if fecha < instalacion.fecha_instalacion:
        raise ErrorNegocio('La fecha de retiro no puede ser anterior a la de instalación.')
    if lectura_retiro < 0:
        raise ErrorNegocio('La lectura de retiro no puede ser negativa.')
    if lectura_retiro < instalacion.lectura_inicial and not aceptar_lectura_menor:
        raise ErrorNegocio('La lectura de retiro es menor que la inicial. Si el contador volvió a cero o hubo '
                           'otra situación, confírmelo explicando el motivo.', codigo='lectura_menor')
    if estado_medidor not in (Medidor.Estado.RETIRADO, Medidor.Estado.DANADO, Medidor.Estado.BAJA,
                              Medidor.Estado.DISPONIBLE):
        raise ErrorNegocio('Estado del medidor retirado inválido.')
    instalacion.fecha_retiro = fecha
    instalacion.lectura_retiro = lectura_retiro
    instalacion.motivo_retiro = motivo
    instalacion.retirado_por = usuario
    instalacion.save(update_fields=['fecha_retiro', 'lectura_retiro', 'motivo_retiro', 'retirado_por', 'actualizado_en'])
    medidor = instalacion.medidor
    medidor.estado = estado_medidor
    medidor.save(update_fields=['estado', 'actualizado_en'])


def _foto_instalacion(i: InstalacionMedidor) -> dict:
    return {'medidor': i.medidor.Code, 'fecha_instalacion': i.fecha_instalacion.isoformat(),
            'lectura_inicial': str(i.lectura_inicial),
            'fecha_retiro': i.fecha_retiro.isoformat() if i.fecha_retiro else None,
            'lectura_retiro': str(i.lectura_retiro) if i.lectura_retiro is not None else None}


def instalar_medidor(conexion: Conexion, medidor: Medidor, *, fecha, lectura_inicial: Decimal, usuario=None,
                     observaciones='', request=None) -> InstalacionMedidor:
    with transaction.atomic():
        conexion = Conexion.objects.select_for_update().get(pk=conexion.pk)
        medidor = Medidor.objects.select_for_update().get(pk=medidor.pk)
        validar_misma_institucion(conexion.institucion, medidor)
        if conexion.estado in SIN_INSTALACION:
            raise ErrorNegocio(f'La conexión está «{conexion.get_estado_display()}»: no se le puede instalar un medidor.')
        if conexion.instalaciones.filter(fecha_retiro__isnull=True).exists():
            raise ErrorNegocio('La conexión ya tiene un medidor vigente. Use «Sustituir medidor».',
                               codigo='ya_tiene_medidor')
        ultimo = conexion.instalaciones.filter(fecha_retiro__isnull=False).order_by('-fecha_retiro').first()
        if ultimo is not None and fecha < ultimo.fecha_retiro:
            raise ErrorNegocio(f'La fecha es anterior al último retiro de medidor de esta conexión '
                               f'({ultimo.fecha_retiro:%d/%m/%Y}): los períodos no pueden superponerse.')
        instalacion = _instalar(conexion, medidor, fecha=fecha, lectura_inicial=lectura_inicial, usuario=usuario,
                                observaciones=observaciones)
        registrar('medidor_instalado', request=request, entidad='conexion', entidad_id=conexion.Code,
                  despues=_foto_instalacion(instalacion))
    return instalacion


def retirar_medidor(conexion: Conexion, *, fecha, lectura_retiro: Decimal, motivo: str, usuario=None,
                    estado_medidor=Medidor.Estado.RETIRADO, aceptar_lectura_menor=False, request=None):
    motivo = (motivo or '').strip()
    if not motivo:
        raise ErrorNegocio('Indique el motivo del retiro.')
    with transaction.atomic():
        conexion = Conexion.objects.select_for_update().get(pk=conexion.pk)
        instalacion = (InstalacionMedidor.objects.select_for_update(of=('self',)).select_related('medidor')
                       .filter(conexion=conexion, fecha_retiro__isnull=True).first())
        if instalacion is None:
            raise ErrorNegocio('La conexión no tiene un medidor vigente.')
        antes = _foto_instalacion(instalacion)
        _retirar(instalacion, fecha=fecha, lectura_retiro=lectura_retiro, motivo=motivo, usuario=usuario,
                 estado_medidor=estado_medidor, aceptar_lectura_menor=aceptar_lectura_menor)
        registrar('medidor_retirado', request=request, entidad='conexion', entidad_id=conexion.Code, motivo=motivo,
                  antes=antes, despues=_foto_instalacion(instalacion))
    return instalacion


def sustituir_medidor(conexion: Conexion, nuevo: Medidor, *, fecha, lectura_retiro: Decimal, lectura_inicial: Decimal,
                      motivo: str, usuario=None, estado_medidor_retirado=Medidor.Estado.RETIRADO,
                      aceptar_lectura_menor=False, request=None) -> InstalacionMedidor:
    """Retira el medidor vigente e instala el nuevo en la misma operación (todo o nada)."""
    motivo = (motivo or '').strip()
    if not motivo:
        raise ErrorNegocio('Indique el motivo de la sustitución.')
    with transaction.atomic():
        conexion = Conexion.objects.select_for_update().get(pk=conexion.pk)
        nuevo = Medidor.objects.select_for_update().get(pk=nuevo.pk)
        validar_misma_institucion(conexion.institucion, nuevo)
        if conexion.estado in SIN_INSTALACION:
            raise ErrorNegocio(f'La conexión está «{conexion.get_estado_display()}»: no se le puede instalar un medidor.')
        vigente = (InstalacionMedidor.objects.select_for_update(of=('self',)).select_related('medidor')
                   .filter(conexion=conexion, fecha_retiro__isnull=True).first())
        if vigente is None:
            raise ErrorNegocio('La conexión no tiene un medidor vigente: use «Instalar medidor».')
        if vigente.medidor_id == nuevo.pk:
            raise ErrorNegocio('El medidor nuevo es el mismo que el actual.')
        antes = _foto_instalacion(vigente)
        _retirar(vigente, fecha=fecha, lectura_retiro=lectura_retiro, motivo=motivo, usuario=usuario,
                 estado_medidor=estado_medidor_retirado, aceptar_lectura_menor=aceptar_lectura_menor)
        instalacion = _instalar(conexion, nuevo, fecha=fecha, lectura_inicial=lectura_inicial, usuario=usuario)
        registrar('medidor_sustituido', request=request, entidad='conexion', entidad_id=conexion.Code, motivo=motivo,
                  antes=antes, despues=_foto_instalacion(instalacion))
    return instalacion
