"""
Recorridos de lectura (sección 8.3): qué conexiones lee cada cobrador en un período.

- Un recorrido es de UN período mensual (AAAA-MM) y se arma por zona, barrio o selección de conexiones.
- Una conexión está en un solo recorrido por período (restricción de base): dos cobradores no leen la misma.
- El orden de visita lo define la oficina (no es alfabético ni por código).
- Se asignan uno o varios cobradores; cada uno registra cuándo inició y finalizó.
- Un cobrador solo ve y lee las conexiones de los recorridos abiertos que tiene asignados.
"""
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

from comun.codigos import campo_code
from comun.modelos import ModeloInstitucional

PERIODO = RegexValidator(r'^\d{4}-(0[1-9]|1[0-2])$', 'Use el formato AAAA-MM (ej. 2026-10).')


class Recorrido(ModeloInstitucional):
    class Estado(models.TextChoices):
        PLANIFICADO = 'planificado', 'Planificado'
        ABIERTO = 'abierto', 'Abierto (los cobradores trabajan)'
        CERRADO = 'cerrado', 'Cerrado'
        ANULADO = 'anulado', 'Anulado'

    Code = campo_code('código del recorrido')
    nombre = models.CharField('nombre', max_length=120)
    periodo = models.CharField('período (AAAA-MM)', max_length=7, validators=[PERIODO], db_index=True,
                               help_text='No se cambia después del alta.')
    estado = models.CharField('estado', max_length=12, choices=Estado.choices, default=Estado.PLANIFICADO,
                              db_index=True)
    fecha_desde = models.DateField('desde', null=True, blank=True)
    fecha_hasta = models.DateField('hasta', null=True, blank=True)
    observaciones = models.TextField('observaciones', blank=True)

    class Meta:
        verbose_name = 'recorrido'
        verbose_name_plural = 'recorridos'
        ordering = ['-periodo', 'nombre']
        constraints = [models.UniqueConstraint(fields=['institucion', 'Code'], name='recorrido_code_unico')]

    def __str__(self):
        return f'{self.Code} · {self.nombre} ({self.periodo})'


class AsignacionRecorrido(ModeloInstitucional):
    """Cobrador autorizado en un recorrido, con su inicio y fin de trabajo."""

    recorrido = models.ForeignKey(Recorrido, on_delete=models.PROTECT, related_name='asignaciones',
                                  verbose_name='recorrido')
    cobrador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='asignaciones',
                                 verbose_name='cobrador')
    activa = models.BooleanField('activa', default=True)
    iniciado_en = models.DateTimeField('inició', null=True, blank=True)
    finalizado_en = models.DateTimeField('finalizó', null=True, blank=True)

    class Meta:
        verbose_name = 'asignación de recorrido'
        verbose_name_plural = 'asignaciones de recorridos'
        constraints = [models.UniqueConstraint(fields=['recorrido', 'cobrador'], name='asignacion_unica')]


class ConexionRecorrido(ModeloInstitucional):
    """Conexión incluida en un recorrido, con su orden de visita."""

    recorrido = models.ForeignKey(Recorrido, on_delete=models.PROTECT, related_name='paradas', verbose_name='recorrido')
    conexion = models.ForeignKey('padron.Conexion', on_delete=models.PROTECT, related_name='en_recorridos',
                                 verbose_name='conexión')
    periodo = models.CharField('período', max_length=7, editable=False)  # copia del recorrido, para la unicidad
    orden = models.PositiveIntegerField('orden de visita', default=0)

    class Meta:
        verbose_name = 'conexión del recorrido'
        verbose_name_plural = 'conexiones del recorrido'
        ordering = ['orden', 'id']
        constraints = [
            models.UniqueConstraint(fields=['recorrido', 'conexion'], name='conexion_una_vez_por_recorrido'),
            # Una conexión en un solo recorrido por período (D25).
            models.UniqueConstraint(fields=['conexion', 'periodo'], name='conexion_un_recorrido_por_periodo'),
        ]
