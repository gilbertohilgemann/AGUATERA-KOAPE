"""
Registro de auditoría (sección 6.3): de SOLO INSERCIÓN.

Ni la aplicación ni el admin pueden modificarlo o borrarlo: `save()` rechaza cambios sobre un
registro existente, `delete()` se niega y la consulta bloquea `update()`/`delete()` masivos.
(Un administrador con acceso directo a la base siempre puede alterar datos: por eso además se
respalda todos los días.)
"""
from django.conf import settings
from django.db import models


class AuditoriaInmutable(Exception):
    pass


class ConsultaAuditoria(models.QuerySet):
    def update(self, **kwargs):
        raise AuditoriaInmutable('La auditoría no se puede modificar.')

    def delete(self):
        raise AuditoriaInmutable('La auditoría no se puede borrar.')

    def de(self, institucion):
        if institucion is None:
            return self.none()
        return self.filter(institucion=institucion)


class RegistroAuditoria(models.Model):
    class Resultado(models.TextChoices):
        EXITO = 'exito', 'Éxito'
        FALLO = 'fallo', 'Fallo'

    institucion = models.ForeignKey(
        'plataforma.Institucion', null=True, blank=True, on_delete=models.PROTECT, related_name='+',
        verbose_name='institución', help_text='Vacío = evento de la plataforma.',
    )
    ocurrido_en = models.DateTimeField('fecha y hora', auto_now_add=True, db_index=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+',
        verbose_name='usuario',
    )
    usuario_nombre = models.CharField('usuario (texto)', max_length=180, blank=True)
    accion = models.CharField('acción', max_length=80, db_index=True)
    entidad = models.CharField('tipo de entidad', max_length=80, blank=True)
    entidad_id = models.CharField('ID de la entidad', max_length=64, blank=True)
    resultado = models.CharField('resultado', max_length=6, choices=Resultado.choices, default=Resultado.EXITO)
    motivo = models.TextField('motivo', blank=True)
    antes = models.JSONField('datos anteriores', null=True, blank=True)
    despues = models.JSONField('datos posteriores', null=True, blank=True)
    detalle = models.JSONField('detalle', default=dict, blank=True)
    ip = models.GenericIPAddressField('IP', null=True, blank=True)
    id_solicitud = models.CharField('ID de solicitud', max_length=64, blank=True)

    objects = ConsultaAuditoria.as_manager()

    class Meta:
        verbose_name = 'registro de auditoría'
        verbose_name_plural = 'auditoría'
        ordering = ['-ocurrido_en', '-id']
        indexes = [models.Index(fields=['institucion', '-ocurrido_en'])]

    def __str__(self):
        return f'{self.ocurrido_en:%d/%m/%Y %H:%M} · {self.usuario_nombre or "-"} · {self.accion}'

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditoriaInmutable('La auditoría no se puede modificar.')
        # force_insert: un objeto nuevo con el pk de uno existente NO puede pisarlo (sería un UPDATE).
        kwargs['force_insert'] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditoriaInmutable('La auditoría no se puede borrar.')
