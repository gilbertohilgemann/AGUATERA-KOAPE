"""Reglas de ingreso, sesión y administración de usuarios."""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.servicios import registrar
from apps.plataforma.models import Institucion

from .models import Usuario
from .permisos import permisos_efectivos
from .tokens import crear_token, revocar_todos

MENSAJE_GENERICO = 'Datos de ingreso incorrectos o usuario bloqueado temporalmente.'
_HASH_FALSO = None


class ErrorIngreso(Exception):
    def __init__(self, mensaje: str = MENSAJE_GENERICO, estado_http: int = 400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.estado_http = estado_http


def _gastar_tiempo_como_si_verificara(contrasena: str) -> None:
    """Iguala el tiempo de respuesta cuando no hay usuario/institución (no se puede adivinar por la demora)."""
    global _HASH_FALSO
    if _HASH_FALSO is None:
        _HASH_FALSO = make_password('koape-hash-de-relleno')
    check_password(contrasena or '', _HASH_FALSO)


def _fallo(request, nombre: str, motivo: str, *, institucion=None, usuario=None):
    registrar('ingreso_fallido', request=request, institucion=institucion, usuario=usuario,
              resultado=RegistroAuditoria.Resultado.FALLO, motivo=motivo, entidad='sesion',
              usuario_nombre=nombre[:180])


def ingresar(request, *, codigo_institucion: str, usuario: str, contrasena: str):
    """
    Valida código institucional + usuario + contraseña. Devuelve (usuario, token, clave).
    Cualquier error de credenciales devuelve el mismo mensaje (no revela qué dato falló).
    """
    codigo = (codigo_institucion or '').strip().upper()
    nombre = (usuario or '').strip().lower()
    institucion = Institucion.objects.filter(codigo=codigo).first()
    if institucion is None:
        _gastar_tiempo_como_si_verificara(contrasena)
        _fallo(request, f'{codigo}/{nombre}', 'Código institucional inexistente.')
        raise ErrorIngreso()

    cuenta = Usuario.objects.filter(institucion=institucion, nombre_usuario=nombre).first()
    if cuenta is None:
        _gastar_tiempo_como_si_verificara(contrasena)
        _fallo(request, f'{codigo}/{nombre}', 'Usuario inexistente.', institucion=institucion)
        raise ErrorIngreso()

    ahora = timezone.now()
    if cuenta.bloqueado_hasta and cuenta.bloqueado_hasta > ahora:
        _gastar_tiempo_como_si_verificara(contrasena)
        _fallo(request, cuenta.identificador, 'Usuario bloqueado temporalmente.', institucion=institucion, usuario=cuenta)
        raise ErrorIngreso()

    if not cuenta.check_password(contrasena):
        with transaction.atomic():
            cuenta = Usuario.objects.select_for_update().get(pk=cuenta.pk)
            cuenta.intentos_fallidos += 1
            if cuenta.intentos_fallidos >= settings.KOAPE['INTENTOS_INGRESO_MAXIMOS']:
                cuenta.bloqueado_hasta = ahora + timedelta(minutes=settings.KOAPE['MINUTOS_BLOQUEO_INGRESO'])
                cuenta.intentos_fallidos = 0
            cuenta.save(update_fields=['intentos_fallidos', 'bloqueado_hasta'])
        _fallo(request, cuenta.identificador, 'Contraseña incorrecta.', institucion=institucion, usuario=cuenta)
        raise ErrorIngreso()

    if not cuenta.is_active:
        _fallo(request, cuenta.identificador, 'Usuario desactivado.', institucion=institucion, usuario=cuenta)
        raise ErrorIngreso()

    if not institucion.esta_activa:
        _fallo(request, cuenta.identificador, f'Institución {institucion.get_estado_display().lower()}.',
               institucion=institucion, usuario=cuenta)
        raise ErrorIngreso('La institución está suspendida. Contacte al administrador de la plataforma.', 403)

    with transaction.atomic():
        cuenta.intentos_fallidos = 0
        cuenta.bloqueado_hasta = None
        cuenta.last_login = ahora
        cuenta.save(update_fields=['intentos_fallidos', 'bloqueado_hasta', 'last_login'])
        token, clave = crear_token(cuenta, request)
        registrar('ingreso', request=request, usuario=cuenta, institucion=institucion,
                  entidad='sesion')
    return cuenta, token, clave


def datos_sesion(usuario, token) -> dict:
    institucion = token.institucion
    return {
        'usuario': {
            'id': usuario.pk,
            'usuario': usuario.nombre_usuario,
            'nombre': usuario.nombre,
            'apellido': usuario.apellido,
            'correo': usuario.correo,
            'es_admin_institucion': usuario.es_admin_institucion,
            'debe_cambiar_contrasena': usuario.debe_cambiar_contrasena,
        },
        'institucion': {
            'codigo': institucion.codigo,
            'nombre': institucion.nombre,
            'estado': institucion.estado,
            'logo': institucion.logo.url if institucion.logo else None,
            'lecturas_permite_galeria': institucion.lecturas_permite_galeria,
        },
        'permisos': sorted(permisos_efectivos(usuario)),
        'sesion_vence_en': token.expira_en.isoformat(),
    }


def cambiar_contrasena(request, usuario, nueva: str) -> int:
    with transaction.atomic():
        usuario.set_password(nueva)
        usuario.debe_cambiar_contrasena = False
        usuario.save(update_fields=['password', 'debe_cambiar_contrasena', *anular_recuperacion(usuario)])
        cerradas = revocar_todos(usuario, excepto=request.auth)
        registrar('cambio_contrasena', request=request, entidad='usuario', entidad_id=usuario.nombre_usuario,
                  sesiones_cerradas=cerradas)
    return cerradas


def restablecer_contrasena(request, usuario, nueva: str) -> None:
    """Lo hace un administrador: el usuario deberá cambiarla al ingresar y se cierran sus sesiones."""
    with transaction.atomic():
        usuario.set_password(nueva)
        usuario.debe_cambiar_contrasena = True
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
        usuario.save(update_fields=['password', 'debe_cambiar_contrasena', 'intentos_fallidos', 'bloqueado_hasta',
                                    *anular_recuperacion(usuario)])
        revocar_todos(usuario)
        registrar('contrasena_restablecida', request=request, entidad='usuario', entidad_id=usuario.nombre_usuario,
                  usuario_afectado=usuario.identificador)


def foto_usuario(usuario) -> dict:
    """Datos de un usuario para guardar como «antes/después» en la auditoría."""
    return {
        'usuario': usuario.nombre_usuario, 'nombre': usuario.nombre, 'apellido': usuario.apellido,
        'correo': usuario.correo, 'activo': usuario.is_active, 'es_admin_institucion': usuario.es_admin_institucion,
        'roles': sorted(usuario.roles.values_list('nombre', flat=True)) if usuario.pk else [],
    }


def foto_rol(rol) -> dict:
    return {
        'Code': rol.Code, 'nombre': rol.nombre, 'descripcion': rol.descripcion, 'activo': rol.activo,
        'permisos': sorted(rol.permisos.values_list('codigo', flat=True)) if rol.pk else [],
    }


# --- Recuperar la contraseña por correo (sección 5.2, D51) ------------------------------------------------------

VIGENCIA_CODIGO = timedelta(minutes=15)
INTENTOS_CODIGO = 5                      # errores por cuenta en VENTANA_INTENTOS (sumando todos los códigos)
VENTANA_INTENTOS = timedelta(hours=24)
CAMPOS_RECUPERACION = ['recuperacion_codigo', 'recuperacion_vence_en', 'recuperacion_enviada_en',
                       'recuperacion_intentos']


def anular_recuperacion(usuario) -> list[str]:
    """Un código pendiente deja de servir (contraseña cambiada o restablecida, correo cambiado). Devuelve los
    campos a guardar."""
    usuario.recuperacion_codigo, usuario.recuperacion_vence_en = '', None
    return ['recuperacion_codigo', 'recuperacion_vence_en']
MENSAJE_RECUPERAR = ('Si el usuario existe y tiene un correo registrado, le enviamos un código para elegir una '
                     'contraseña nueva. Vence en 15 minutos (si ya pidió uno, use ese). Si no llega, pida a un '
                     'administrador que la restablezca.')
MENSAJE_CODIGO = 'El código es incorrecto o venció. Pida uno nuevo.'


def _cuenta_recuperable(codigo_institucion: str, usuario: str):
    """Usuario activo de una institución activa, con correo. Los de la plataforma usan el panel de la plataforma."""
    codigo = (codigo_institucion or '').strip().upper()
    nombre = (usuario or '').strip().lower()
    cuenta = (Usuario.objects.select_related('institucion')
              .filter(institucion__codigo=codigo, nombre_usuario=nombre).first()) if codigo and nombre else None
    if cuenta is None or not cuenta.is_active or not cuenta.correo or not cuenta.institucion.esta_activa:
        return None
    return cuenta


def solicitar_recuperacion(request, *, codigo_institucion: str, usuario: str) -> None:
    """Siempre la misma respuesta (no revela qué usuarios existen ni si tienen correo)."""
    import secrets

    from django.template.loader import render_to_string

    from comun.correo import enviar_correo
    codigo = f'{secrets.randbelow(10 ** 6):06d}'
    hash_codigo = make_password(codigo)            # siempre: mismo tiempo de respuesta
    cuenta = _cuenta_recuperable(codigo_institucion, usuario)
    nombre = f'{(codigo_institucion or "").strip().upper()}/{(usuario or "").strip().lower()}'[:180]
    if cuenta is None:
        render_to_string('identidad/recuperar.txt', {'codigo': codigo})   # mismo trabajo que si existiera
        registrar('recuperacion_rechazada', request=request, entidad='usuario', usuario_nombre=nombre,
                  resultado=RegistroAuditoria.Resultado.FALLO, motivo='Usuario inexistente, inactivo o sin correo')
        return
    ahora = timezone.now()
    with transaction.atomic():
        cuenta = Usuario.objects.select_for_update().get(pk=cuenta.pk)
        # - Mientras el código enviado siga vigente no se manda otro: nadie puede anular el código que el usuario ya
        #   tiene en su correo ni llenarle la casilla (la respuesta es la misma).
        # - Los errores se suman entre códigos: 5 en 24 horas y no se envían más hasta que pase ese plazo (no se
        #   puede probar sin fin pidiendo códigos nuevos). Un administrador siempre puede restablecerla.
        if cuenta.recuperacion_vence_en and cuenta.recuperacion_vence_en > ahora:
            return
        reciente = cuenta.recuperacion_enviada_en and ahora - cuenta.recuperacion_enviada_en < VENTANA_INTENTOS
        if not reciente:
            cuenta.recuperacion_intentos = 0
        elif cuenta.recuperacion_intentos >= INTENTOS_CODIGO:
            registrar('recuperacion_rechazada', request=request, institucion=cuenta.institucion, usuario=cuenta,
                      entidad='usuario', entidad_id=cuenta.nombre_usuario,
                      resultado=RegistroAuditoria.Resultado.FALLO, motivo='Demasiados códigos incorrectos en 24 horas')
            return
        cuenta.recuperacion_codigo = hash_codigo
        cuenta.recuperacion_vence_en = ahora + VIGENCIA_CODIGO
        cuenta.recuperacion_enviada_en = ahora
        cuenta.save(update_fields=CAMPOS_RECUPERACION)
        registrar('recuperacion_solicitada', request=request, institucion=cuenta.institucion, usuario=cuenta,
                  entidad='usuario', entidad_id=cuenta.nombre_usuario)
    cuerpo = render_to_string('identidad/recuperar.txt', {
        'nombre': cuenta.get_full_name() if hasattr(cuenta, 'get_full_name') else cuenta.nombre,
        'usuario': cuenta.nombre_usuario, 'institucion': cuenta.institucion.nombre,
        'codigo_institucion': cuenta.institucion.codigo, 'codigo': codigo,
        'minutos': int(VIGENCIA_CODIGO.total_seconds() // 60)})
    enviar_correo('Código para elegir una contraseña nueva', cuerpo, cuenta.correo)


def confirmar_recuperacion(request, *, codigo_institucion: str, usuario: str, codigo: str, nueva: str) -> None:
    """Con el código del correo elige una contraseña nueva: desbloquea el usuario y cierra todas sus sesiones."""
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    from comun.errores import ErrorNegocio
    ahora = timezone.now()
    cuenta = _cuenta_recuperable(codigo_institucion, usuario)
    with transaction.atomic():
        if cuenta is not None:
            cuenta = Usuario.objects.select_for_update().get(pk=cuenta.pk)
        vigente = (cuenta is not None and bool(cuenta.recuperacion_codigo) and cuenta.recuperacion_vence_en
                   and cuenta.recuperacion_vence_en > ahora and cuenta.recuperacion_intentos < INTENTOS_CODIGO)
        if not vigente:
            _gastar_tiempo_como_si_verificara(codigo)
        correcto = bool(vigente) and check_password((codigo or '').strip(), cuenta.recuperacion_codigo)
        if not correcto:
            if vigente:
                cuenta.recuperacion_intentos += 1      # al 5.º error (en 24 h) el código deja de servir
                if cuenta.recuperacion_intentos >= INTENTOS_CODIGO:
                    anular_recuperacion(cuenta)
                cuenta.save(update_fields=CAMPOS_RECUPERACION)
        else:
            try:
                validate_password(nueva or '', user=cuenta)
            except ValidationError as error:
                raise ErrorNegocio(' '.join(error.messages), codigo='contrasena_debil')
            cuenta.set_password(nueva)
            cuenta.debe_cambiar_contrasena = False
            cuenta.intentos_fallidos, cuenta.bloqueado_hasta = 0, None
            cuenta.recuperacion_codigo, cuenta.recuperacion_vence_en, cuenta.recuperacion_intentos = '', None, 0
            cuenta.save(update_fields=['password', 'debe_cambiar_contrasena', 'intentos_fallidos', 'bloqueado_hasta',
                                       'recuperacion_codigo', 'recuperacion_vence_en', 'recuperacion_intentos'])
            cerradas = revocar_todos(cuenta)
            registrar('contrasena_recuperada', request=request, institucion=cuenta.institucion, usuario=cuenta,
                      entidad='usuario', entidad_id=cuenta.nombre_usuario, sesiones_cerradas=cerradas)
    if not correcto:
        registrar('recuperacion_fallida', request=request, entidad='usuario',
                  usuario_nombre=f'{(codigo_institucion or "").strip().upper()}/{(usuario or "").strip().lower()}'[:180],
                  resultado=RegistroAuditoria.Resultado.FALLO, motivo='Código incorrecto o vencido')
        raise ErrorNegocio(MENSAJE_CODIGO, codigo='codigo_invalido')
