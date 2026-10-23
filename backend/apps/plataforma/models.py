"""
Instituciones: cada aguatera, junta de saneamiento u organización prestadora del servicio.

Todo dato de negocio cuelga de una institución (ver `comun/modelos.py`). La institución nunca se
borra: se suspende o se archiva (regla «nada se borra», sección 6 de la especificación).
"""
from django.core.validators import FileExtensionValidator, RegexValidator
from django.db import models


class Institucion(models.Model):
    class Estado(models.TextChoices):
        ACTIVA = 'activa', 'Activa'
        SUSPENDIDA = 'suspendida', 'Suspendida'
        ARCHIVADA = 'archivada', 'Archivada'

    class ModalidadFacturacion(models.TextChoices):
        # La modalidad real depende de las habilitaciones fiscales de cada institución (decisión de
        # negocio pendiente, sección 24): mientras no se configure, el sistema no emite facturas.
        NO_CONFIGURADA = 'no_configurada', 'No configurada'
        ELECTRONICA = 'electronica', 'Electrónica (proveedor externo)'
        AUTOIMPRESA = 'autoimpresa', 'Autoimpresa'

    codigo = models.CharField(
        'código institucional', max_length=20, unique=True,
        validators=[RegexValidator(r'^[A-Z0-9][A-Z0-9-]{1,19}$',
                                   'Use de 2 a 20 letras mayúsculas, números o guiones (ej. JUNTA-SL).')],
        help_text='Lo escriben los usuarios al ingresar. No se puede cambiar después de creada.',
    )
    nombre = models.CharField('nombre o razón social', max_length=200)
    ruc = models.CharField('RUC', max_length=20, blank=True)
    direccion = models.CharField('dirección', max_length=255, blank=True)
    telefono = models.CharField('teléfono', max_length=50, blank=True)
    correo = models.EmailField('correo electrónico', blank=True)
    logo = models.FileField(
        'logo', upload_to='instituciones/logos/', blank=True,
        validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp'])],
    )
    contacto = models.TextField('datos de contacto', blank=True,
                                help_text='Persona responsable, horarios de atención, otros teléfonos.')
    estado = models.CharField('estado', max_length=12, choices=Estado.choices, default=Estado.ACTIVA, db_index=True)
    motivo_estado = models.TextField('motivo del último cambio de estado', blank=True)
    zona_horaria = models.CharField('zona horaria', max_length=60, default='America/Asuncion')
    configuracion_regional = models.CharField('configuración regional', max_length=10, default='es-PY')
    modalidad_facturacion = models.CharField(
        'modalidad de facturación', max_length=16, choices=ModalidadFacturacion.choices,
        default=ModalidadFacturacion.NO_CONFIGURADA,
    )
    configuracion_facturacion = models.JSONField('configuración de facturación', default=dict, blank=True)
    configuracion_tarifas = models.JSONField('configuración de tarifas', default=dict, blank=True)
    dias_vencimiento_credito = models.PositiveSmallIntegerField(
        'días de vencimiento de las facturas a crédito', default=30,
        help_text='La factura a crédito vence esta cantidad de días después de emitida.')
    aplicacion_pagos = models.CharField(
        'reparto de los pagos a crédito', max_length=12, default='manual',
        choices=[('manual', 'Manual: el cajero indica cuánto va a cada factura'),
                 ('automatica', 'Automático: primero la factura vencida más antigua')],
        help_text='Cómo se reparte un cobro entre las facturas a crédito del cliente. Siempre se muestra el reparto '
                  'antes de confirmar.')
    portal_abonados = models.BooleanField(
        'portal de abonados', default=False,
        help_text='Si está activo, los clientes pueden consultar su cuenta (deuda, facturas, pagos, lecturas) en el '
                  'portal, con una cuenta propia por correo. La institución decide si lo ofrece.')
    lecturas_permite_galeria = models.BooleanField(
        'lecturas: permitir foto de la galería', default=False,
        help_text='Por defecto la foto del medidor se toma con la cámara en el momento. Si se habilita, el cobrador '
                  'puede elegir una foto ya tomada y la lectura queda marcada como «foto de galería».',
    )
    creado_en = models.DateTimeField('creada el', auto_now_add=True)
    actualizado_en = models.DateTimeField('actualizada el', auto_now=True)

    class Meta:
        verbose_name = 'institución'
        verbose_name_plural = 'instituciones'
        ordering = ['nombre']

    def __str__(self):
        return f'{self.nombre} ({self.codigo})'

    def save(self, *args, **kwargs):
        self.codigo = (self.codigo or '').strip().upper()
        super().save(*args, **kwargs)

    @property
    def esta_activa(self) -> bool:
        return self.estado == self.Estado.ACTIVA


class Secuencia(models.Model):
    """
    Numeradores INTERNOS por institución. Se incrementan dentro de una transacción con bloqueo de fila:
    dos operaciones simultáneas nunca reciben el mismo número. Nunca se muestran al usuario ni se usan
    como clave visible (convención: los maestros llevan `Code` cargado por el usuario y los documentos
    de formulario continuo `SerNr` tomado de los rangos de su punto de expedición). Excepción documentada
    (D39): la secuencia `recibo` numera el DOCUMENTO recibo, que sí se imprime; no es el id de ningún registro.
    """

    institucion = models.ForeignKey(Institucion, on_delete=models.PROTECT, related_name='+', verbose_name='institución')
    clave = models.CharField('clave', max_length=40)
    ultimo = models.PositiveBigIntegerField('último número', default=0)

    class Meta:
        verbose_name = 'secuencia'
        verbose_name_plural = 'secuencias'
        constraints = [models.UniqueConstraint(fields=['institucion', 'clave'], name='secuencia_unica')]

    def __str__(self):
        return f'{self.institucion.codigo} · {self.clave} = {self.ultimo}'


def siguiente_numero(institucion, clave: str) -> int:
    """Próximo número de la secuencia. Debe llamarse dentro de `transaction.atomic()`."""
    secuencia, _ = Secuencia.objects.select_for_update().get_or_create(institucion=institucion, clave=clave)
    secuencia.ultimo += 1
    secuencia.save(update_fields=['ultimo'])
    return secuencia.ultimo
