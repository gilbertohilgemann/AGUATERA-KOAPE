"""
Portal de abonados: UNA cuenta por persona (identificada por su documento normalizado) para consultar su cuenta de
agua en TODAS las instituciones donde es cliente y que ofrecen el portal.

Decisiones del cliente (21/10/2026): la usan los abonados; se activa con el número de documento y un correo que debe
estar cargado en la ficha del cliente con ese documento en al menos una institución; el PIN temporal llega a ese
correo y, al ingresar con él, la persona elige su contraseña.

No es un usuario del sistema (no tiene permisos ni institución): solo consulta lo suyo, de solo lectura.
"""
from django.db import models


class CuentaAbonado(models.Model):
    documento = models.CharField('documento normalizado', max_length=30, unique=True)
    correo = models.EmailField('correo')
    nombre = models.CharField('nombre', max_length=200, blank=True)
    clave = models.CharField('contraseña (hash)', max_length=128, blank=True)
    pin = models.CharField('PIN temporal (hash)', max_length=128, blank=True)
    pin_vence_en = models.DateTimeField('el PIN vence', null=True, blank=True)
    pin_enviado_en = models.DateTimeField('último PIN enviado', null=True, blank=True)
    debe_cambiar_clave = models.BooleanField('debe elegir contraseña', default=True)
    intentos_fallidos = models.PositiveSmallIntegerField('intentos fallidos', default=0)
    bloqueada_hasta = models.DateTimeField('bloqueada hasta', null=True, blank=True)
    activa = models.BooleanField('activa', default=True)
    creada_en = models.DateTimeField('creada el', auto_now_add=True)
    ultimo_ingreso = models.DateTimeField('último ingreso', null=True, blank=True)

    class Meta:
        verbose_name = 'cuenta de abonado'
        verbose_name_plural = 'cuentas de abonados'
        indexes = [models.Index(fields=['correo'])]

    # La autenticación de DRF trata a la cuenta como «usuario» de la solicitud del portal.
    is_authenticated = True
    is_anonymous = False

    def __str__(self):
        # Así figura en la auditoría: sin el documento completo ni el correo.
        return f'portal:***{self.documento[-3:]}'


class SesionPortal(models.Model):
    cuenta = models.ForeignKey(CuentaAbonado, on_delete=models.CASCADE, related_name='sesiones', verbose_name='cuenta')
    clave_hash = models.CharField('hash del token', max_length=64, unique=True)
    creada_en = models.DateTimeField('creada el', auto_now_add=True)
    vence_en = models.DateTimeField('vence el')
    revocada_en = models.DateTimeField('revocada el', null=True, blank=True)
    ip = models.GenericIPAddressField('IP', null=True, blank=True)

    class Meta:
        verbose_name = 'sesión del portal'
        verbose_name_plural = 'sesiones del portal'
