"""
Pagos y recibos (Fase 6, secciones 11.5, 11.6 y 12).

- `Pago`: el dinero recibido. Nace de dos maneras (decisión del cliente, 21/10/2026):
  · al emitir una factura CONTADO (el pago se registra en el mismo paso y la factura queda pagada);
  · con un RECIBO, para las facturas a CRÉDITO (pagos parciales, varias facturas por pago).
- `AplicacionPago`: cuánto de un pago va a cada factura. El saldo de una factura SE DERIVA de sus aplicaciones vigentes:
  nunca se guarda «pagada» a mano.
- `Recibo`: el comprobante del cobro a crédito (no reemplaza a la factura fiscal).

Nada se borra ni se modifica en silencio: un recibo se ANULA (con motivo) y su pago queda REVERTIDO, conservando el
original. La caja (Fase 7) registrará el movimiento compensatorio.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from comun.codigos import campo_code
from comun.modelos import ModeloInstitucional

IMPORTE = {'max_digits': 18, 'decimal_places': 2}


class FormaPago(ModeloInstitucional):
    """Formas de pago de la institución (efectivo, transferencia, POS, otras). Se desactivan, no se borran."""

    class Tipo(models.TextChoices):
        EFECTIVO = 'efectivo', 'Efectivo'
        TRANSFERENCIA = 'transferencia', 'Transferencia'
        POS = 'pos', 'POS (tarjeta)'
        OTRO = 'otro', 'Otro medio'

    Code = campo_code()
    nombre = models.CharField('nombre', max_length=80)
    tipo = models.CharField('tipo', max_length=15, choices=Tipo.choices, default=Tipo.OTRO,
                            help_text='La caja muestra un saldo separado por tipo: no se suman como dinero físico.')
    requiere_referencia = models.BooleanField('pide referencia', default=False,
                                              help_text='Ej. número de transferencia o de voucher del POS.')
    orden = models.PositiveSmallIntegerField('orden', default=0)
    activa = models.BooleanField('activa', default=True)

    class Meta:
        verbose_name = 'forma de pago'
        verbose_name_plural = 'formas de pago'
        ordering = ['orden', 'nombre']
        constraints = [models.UniqueConstraint(fields=['institucion', 'Code'], name='forma_pago_code_unico')]

    def __str__(self):
        return self.nombre


FORMAS_INICIALES = [
    # (Code, nombre, tipo, requiere_referencia, orden)
    ('EFECTIVO', 'Efectivo', 'efectivo', False, 1),
    ('TRANSFERENCIA', 'Transferencia', 'transferencia', True, 2),
    ('POS', 'POS (tarjeta)', 'pos', True, 3),
]


class Pago(ModeloInstitucional):
    class Origen(models.TextChoices):
        CONTADO = 'contado', 'Factura contado'
        RECIBO = 'recibo', 'Recibo'

    class Estado(models.TextChoices):
        CONFIRMADO = 'confirmado', 'Confirmado'
        REVERTIDO = 'revertido', 'Revertido'

    referencia = models.CharField('referencia', max_length=12)
    cliente = models.ForeignKey('padron.Cliente', on_delete=models.PROTECT, related_name='pagos', verbose_name='cliente')
    fecha_hora = models.DateTimeField('fecha y hora')
    importe = models.DecimalField('importe', **IMPORTE)
    forma_pago = models.ForeignKey(FormaPago, on_delete=models.PROTECT, related_name='pagos', verbose_name='forma de pago')
    referencia_externa = models.CharField('referencia de la operación', max_length=100, blank=True)
    origen = models.CharField('origen', max_length=10, choices=Origen.choices)
    estado = models.CharField('estado', max_length=12, choices=Estado.choices, default=Estado.CONFIRMADO, db_index=True)
    observaciones = models.TextField('observaciones', blank=True)
    clave_idempotencia = models.CharField('clave de idempotencia', max_length=64)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+',
                                verbose_name='cobrado por')
    sesion = models.ForeignKey('caja.SesionCaja', on_delete=models.PROTECT, null=True, blank=True,
                               related_name='pagos', verbose_name='sesión de caja',
                               help_text='Vacío solo en cobros anteriores a la caja (Fase 7).')
    revertido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                      related_name='+', verbose_name='revertido por')
    revertido_en = models.DateTimeField('revertido el', null=True, blank=True)
    motivo_reversion = models.TextField('motivo de la reversión', blank=True)

    class Meta:
        verbose_name = 'pago'
        verbose_name_plural = 'pagos'
        ordering = ['-fecha_hora']
        constraints = [
            models.UniqueConstraint(fields=['institucion', 'referencia'], name='pago_referencia_unica'),
            # Un reintento de red con la misma clave nunca crea un segundo pago.
            models.UniqueConstraint(fields=['institucion', 'clave_idempotencia'], name='pago_idempotente'),
            models.CheckConstraint(condition=Q(importe__gt=0), name='pago_importe_positivo'),
        ]

    def __str__(self):
        return f'{self.referencia} · {self.importe}'


class AplicacionPago(ModeloInstitucional):
    class Estado(models.TextChoices):
        VIGENTE = 'vigente', 'Vigente'
        REVERTIDA = 'revertida', 'Revertida'

    pago = models.ForeignKey(Pago, on_delete=models.PROTECT, related_name='aplicaciones', verbose_name='pago')
    factura = models.ForeignKey('facturacion.Factura', on_delete=models.PROTECT, related_name='aplicaciones_pago',
                                verbose_name='factura')
    importe = models.DecimalField('importe aplicado', **IMPORTE)
    saldo_anterior = models.DecimalField('saldo de la factura antes del pago', **IMPORTE)
    estado = models.CharField('estado', max_length=10, choices=Estado.choices, default=Estado.VIGENTE, db_index=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+',
                                verbose_name='usuario')

    class Meta:
        verbose_name = 'aplicación de pago'
        verbose_name_plural = 'aplicaciones de pagos'
        ordering = ['pk']
        constraints = [
            models.CheckConstraint(condition=Q(importe__gt=0), name='aplicacion_importe_positivo'),
            models.UniqueConstraint(fields=['pago', 'factura'], name='aplicacion_unica_por_factura'),
        ]


class Recibo(ModeloInstitucional):
    """Recibo de cobro de facturas a crédito. Número correlativo propio de la institución (no es documento fiscal)."""

    class Estado(models.TextChoices):
        EMITIDO = 'emitido', 'Emitido'
        ANULADO = 'anulado', 'Anulado'

    numero = models.PositiveIntegerField('número')
    pago = models.OneToOneField(Pago, on_delete=models.PROTECT, related_name='recibo', verbose_name='pago')
    cliente = models.ForeignKey('padron.Cliente', on_delete=models.PROTECT, related_name='recibos',
                                verbose_name='cliente')
    cliente_nombre = models.CharField('nombre del cliente', max_length=200)
    cliente_documento = models.CharField('RUC / C.I.', max_length=30, blank=True)
    fecha_hora = models.DateTimeField('fecha y hora')
    importe = models.DecimalField('importe recibido', **IMPORTE)
    saldo_restante = models.DecimalField('saldo del cliente después del cobro', **IMPORTE)
    estado = models.CharField('estado', max_length=10, choices=Estado.choices, default=Estado.EMITIDO, db_index=True)
    anulado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='+', verbose_name='anulado por')
    anulado_en = models.DateTimeField('anulado el', null=True, blank=True)
    motivo_anulacion = models.TextField('motivo de la anulación', blank=True)

    class Meta:
        verbose_name = 'recibo'
        verbose_name_plural = 'recibos'
        ordering = ['-numero']
        constraints = [models.UniqueConstraint(fields=['institucion', 'numero'], name='recibo_numero_unico')]

    @property
    def numero_impreso(self) -> str:
        return f'{self.numero:07d}'

    def __str__(self):
        return f'Recibo {self.numero_impreso}'
