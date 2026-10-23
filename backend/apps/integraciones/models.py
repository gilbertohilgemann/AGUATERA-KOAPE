"""
Credenciales de integración (sección 16): para que otro sistema (ej. un ERP) consulte la API de UNA institución.

Decisiones del cliente (21/10/2026): las crea el administrador de cada institución; en esta versión son de SOLO
LECTURA. La clave se muestra una sola vez al crearla y se guarda solo su hash; se puede revocar en cualquier momento.
Cada solicitud queda registrada y hay un límite de solicitudes por minuto.
"""
from django.conf import settings
from django.db import models

from comun.modelos import ModeloInstitucional


class CredencialIntegracion(ModeloInstitucional):
    nombre = models.CharField('nombre (para qué sistema es)', max_length=120)
    prefijo = models.CharField('identificador visible', max_length=12, unique=True)
    clave_hash = models.CharField('hash de la clave', max_length=64, unique=True)
    permisos = models.JSONField('permisos de lectura', default=list)
    limite_por_minuto = models.PositiveSmallIntegerField('solicitudes por minuto', default=60)
    expira_en = models.DateTimeField('vence el', null=True, blank=True)
    activa = models.BooleanField('activa', default=True)
    creada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+',
                                   verbose_name='creada por')
    revocada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='+', verbose_name='revocada por')
    revocada_en = models.DateTimeField('revocada el', null=True, blank=True)
    motivo_revocacion = models.TextField('motivo de la revocación', blank=True)
    ultimo_uso_en = models.DateTimeField('último uso', null=True, blank=True)

    class Meta:
        verbose_name = 'credencial de integración'
        verbose_name_plural = 'credenciales de integración'
        ordering = ['-creado_en']

    def __str__(self):
        return f'{self.nombre} ({self.prefijo})'


class RegistroSolicitudIntegracion(models.Model):
    """Cada solicitud hecha con una credencial (solo inserción)."""

    credencial = models.ForeignKey(CredencialIntegracion, on_delete=models.PROTECT, related_name='registros',
                                   verbose_name='credencial')
    fecha_hora = models.DateTimeField('fecha y hora', auto_now_add=True, db_index=True)
    metodo = models.CharField('método', max_length=8)
    ruta = models.CharField('ruta', max_length=300)
    estado = models.PositiveSmallIntegerField('respuesta HTTP')
    ip = models.GenericIPAddressField('IP', null=True, blank=True)
    duracion_ms = models.PositiveIntegerField('duración (ms)', default=0)
    id_solicitud = models.CharField('id de solicitud', max_length=64, blank=True)

    class Meta:
        verbose_name = 'solicitud de integración'
        verbose_name_plural = 'solicitudes de integración'
        ordering = ['-fecha_hora']
