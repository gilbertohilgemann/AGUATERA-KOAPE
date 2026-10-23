"""
Reglas del portal de abonados: activación con documento + correo del padrón, PIN temporal por correo, contraseña
propia, sesión y qué clientes «son» de la cuenta en cada institución.

Seguridad:
- Las respuestas de «enviar PIN» e «ingresar» son siempre iguales, coincidan o no los datos, y hacen el mismo trabajo
  (no revelan quién es cliente ni quién tiene cuenta).
- La persona ve una institución solo si su ficha ahí tiene ESE documento y ESE correo (un documento repetido o mal
  cargado en otra institución no muestra datos ajenos). Los documentos de relleno («0», «S/N»…) no sirven.
- El PIN (6 dígitos) vence a los 15 minutos, se guarda solo su hash y se usa una vez. Hay espera entre envíos.
- Tras 5 intentos fallidos la cuenta queda bloqueada 15 minutos.
"""
import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.auditoria.servicios import registrar
from apps.identidad.tokens import hash_de
from comun.correo import enviar_correo
from comun.documentos import documento_identificable, normalizar_documento
from comun.errores import ErrorNegocio

from .models import CuentaAbonado, SesionPortal

VIGENCIA_PIN = timedelta(minutes=15)
ESPERA_ENTRE_PINES = timedelta(seconds=60)
INTENTOS_MAXIMOS = 5
BLOQUEO = timedelta(minutes=15)
VIGENCIA_SESION = timedelta(hours=8)
MENSAJE_ENVIO = ('Si los datos coinciden con los de su junta o aguatera, le enviamos un PIN a ese correo. '
                 'Vence en 15 minutos. Si no llega, revise «correo no deseado» o consulte en la oficina.')
MENSAJE_INGRESO = ('Datos incorrectos. Verifique su número de documento (o correo) y su contraseña o PIN. Tras 5 intentos '
                   'fallidos la cuenta se bloquea 15 minutos.')


def clientes_de(documento: str, correo: str, *, institucion=None):
    """Fichas de cliente de esa persona (mismo documento Y mismo correo) en las instituciones con portal (activas)."""
    from apps.padron.models import Cliente
    from apps.plataforma.models import Institucion
    consulta = (Cliente.objects.filter(documento_normalizado=documento, correo__iexact=(correo or '').strip(),
                                       institucion__portal_abonados=True, institucion__estado=Institucion.Estado.ACTIVA)
                .exclude(estado=Cliente.Estado.ARCHIVADO).select_related('institucion'))
    if not documento_identificable(documento) or not (correo or '').strip():
        return consulta.none()
    if institucion is not None:
        consulta = consulta.filter(institucion=institucion)
    return consulta


def clientes_de_cuenta(cuenta: CuentaAbonado, *, institucion=None):
    return clientes_de(cuenta.documento, cuenta.correo, institucion=institucion)


def solicitar_pin(*, documento: str, correo: str, request=None) -> None:
    """Activar o recuperar la cuenta. Solo envía si el correo figura en la ficha de un cliente con ese documento."""
    documento = normalizar_documento(documento)
    correo = (correo or '').strip().lower()
    if not documento or not correo:
        raise ErrorNegocio('Escriba su número de documento y su correo.')
    pin = f'{secrets.randbelow(10 ** 6):06d}'
    hash_pin = make_password(pin)          # siempre (también si no coincide): mismo tiempo de respuesta
    coincidencias = list(clientes_de(documento, correo))
    if not coincidencias:
        registrar('portal_pin_rechazado', request=request, entidad='cuenta_abonado', entidad_id=_oculto(documento),
                  resultado='fallo', motivo='El correo no figura en el padrón con ese documento')
        return  # misma respuesta que si se envió: no se revela si es cliente
    ahora = timezone.now()
    with transaction.atomic():
        cuenta, _ = CuentaAbonado.objects.select_for_update().get_or_create(
            documento=documento, defaults={'correo': correo, 'nombre': coincidencias[0].nombre})
        if not cuenta.activa or (cuenta.pin_enviado_en and ahora - cuenta.pin_enviado_en < ESPERA_ENTRE_PINES):
            # Pidió otro hace menos de un minuto: no se reenvía, pero la respuesta es la misma (el mensaje ya
            # avisa que puede tardar).
            registrar('portal_pin_rechazado', request=request, entidad='cuenta_abonado',
                      entidad_id=_oculto(documento), resultado='fallo', motivo='Pedido repetido o cuenta inactiva')
            return
        cuenta.correo = correo            # el último correo verificado en el padrón
        cuenta.pin = hash_pin
        cuenta.pin_vence_en = ahora + VIGENCIA_PIN
        cuenta.pin_enviado_en = ahora
        cuenta.save()
    contexto = {'nombre': cuenta.nombre, 'pin': pin, 'minutos': int(VIGENCIA_PIN.total_seconds() // 60),
                'instituciones': sorted({c.institucion.nombre for c in coincidencias})}
    _enviar_correo('Su PIN para consultar su cuenta de agua', render_to_string('portal/pin.txt', contexto), correo)
    registrar('portal_pin_enviado', request=request, entidad='cuenta_abonado', entidad_id=_oculto(documento))


def _enviar_correo(asunto: str, cuerpo: str, destino: str) -> None:
    enviar_correo(asunto, cuerpo, destino)


def _oculto(documento: str) -> str:
    """En la auditoría el documento va parcialmente oculto."""
    return f'***{documento[-3:]}' if len(documento) > 3 else '***'


def _buscar(usuario: str) -> CuentaAbonado | None:
    """Por documento o por correo. Un correo de varias cuentas (familiares) no identifica a nadie: se ingresa con el
    documento (el mensaje de error genérico ya lo sugiere)."""
    usuario = (usuario or '').strip()
    if '@' in usuario:
        cuentas = list(CuentaAbonado.objects.filter(correo__iexact=usuario)[:2])
        return cuentas[0] if len(cuentas) == 1 else None
    return CuentaAbonado.objects.filter(documento=normalizar_documento(usuario)).first()


_RELLENO = make_password('relleno-de-tiempo')


def ingresar(*, usuario: str, clave: str, request=None) -> tuple[CuentaAbonado, str]:
    """Con el PIN (la primera vez o al recuperar) o con su contraseña. Devuelve la cuenta y el token de sesión."""
    ahora = timezone.now()
    with transaction.atomic():
        cuenta = _buscar(usuario)
        if cuenta is not None:
            cuenta = CuentaAbonado.objects.select_for_update().get(pk=cuenta.pk)
        # Siempre se comparan dos hashes (PIN y contraseña, o rellenos): el tiempo no revela si la cuenta existe,
        # si está bloqueada ni si tiene contraseña. Bloqueada o inexistente responden igual que un dato incorrecto.
        pin_vigente = cuenta is not None and bool(cuenta.pin) and cuenta.pin_vence_en and cuenta.pin_vence_en > ahora
        ok_pin = check_password(clave or '', cuenta.pin if pin_vigente else _RELLENO) and bool(pin_vigente)
        ok_clave = check_password(clave or '', cuenta.clave if cuenta is not None and cuenta.clave else _RELLENO) \
            and cuenta is not None and bool(cuenta.clave)
        if cuenta is None or not cuenta.activa:
            raise ErrorNegocio(MENSAJE_INGRESO, codigo='ingreso_invalido')
        bloqueada = bool(cuenta.bloqueada_hasta and cuenta.bloqueada_hasta > ahora)
        con_pin = ok_pin and not bloqueada
        con_clave = not con_pin and ok_clave and not bloqueada
        fallo = not (con_pin or con_clave)
        if fallo:
            if not bloqueada:
                # Se guarda y RECIÉN después se informa el error (si se lanzara aquí, la transacción lo desharía).
                cuenta.intentos_fallidos += 1
                if cuenta.intentos_fallidos >= INTENTOS_MAXIMOS:
                    cuenta.bloqueada_hasta, cuenta.intentos_fallidos = ahora + BLOQUEO, 0
                cuenta.save(update_fields=['intentos_fallidos', 'bloqueada_hasta'])
        else:
            token = _abrir_sesion(cuenta, bool(con_pin), ahora, request)
    if fallo:
        registrar('portal_ingreso_fallido', request=request, entidad='cuenta_abonado',
                  entidad_id=_oculto(cuenta.documento), resultado='fallo')
        raise ErrorNegocio(MENSAJE_INGRESO, codigo='ingreso_invalido')
    registrar('portal_ingreso', request=request, entidad='cuenta_abonado', entidad_id=_oculto(cuenta.documento),
              con_pin=bool(con_pin))
    return cuenta, token


def _abrir_sesion(cuenta, con_pin, ahora, request) -> str:
    """Se llama dentro de la transacción de `ingresar` (PIN de un solo uso, sesión nueva)."""
    if con_pin:
        cuenta.pin, cuenta.pin_vence_en = '', None   # se usa una sola vez
        cuenta.debe_cambiar_clave = True
    cuenta.intentos_fallidos, cuenta.bloqueada_hasta, cuenta.ultimo_ingreso = 0, None, ahora
    cuenta.save()
    token = secrets.token_urlsafe(32)
    SesionPortal.objects.create(cuenta=cuenta, clave_hash=hash_de(token), vence_en=ahora + VIGENCIA_SESION,
                                ip=(request.META.get('REMOTE_ADDR') if request is not None else None))
    return token


def cambiar_clave(cuenta: CuentaAbonado, *, nueva: str, actual: str = '', sesion=None, request=None) -> None:
    if not cuenta.debe_cambiar_clave and not check_password(actual or '', cuenta.clave):
        raise ErrorNegocio('La contraseña actual no es correcta.', codigo='clave_actual')
    try:
        validate_password(nueva or '')
    except ValidationError as error:
        raise ErrorNegocio(' '.join(error.messages), codigo='clave_debil')
    with transaction.atomic():
        cuenta.clave = make_password(nueva)
        cuenta.debe_cambiar_clave = False
        cuenta.save(update_fields=['clave', 'debe_cambiar_clave'])
        # Se cierran las demás sesiones (ej. si alguien más tenía el PIN).
        SesionPortal.objects.filter(cuenta=cuenta, revocada_en__isnull=True).exclude(pk=getattr(sesion, 'pk', None)) \
            .update(revocada_en=timezone.now())
    registrar('portal_clave_cambiada', request=request, entidad='cuenta_abonado', entidad_id=_oculto(cuenta.documento))


def salir(sesion: SesionPortal) -> None:
    SesionPortal.objects.filter(pk=sesion.pk).update(revocada_en=timezone.now())
