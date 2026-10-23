"""
Caja diaria y gastos referenciales (Fase 7, secciones 13 y 14).

Decisiones del cliente (21/10/2026): para cobrar hace falta la caja ABIERTA; cada cajero abre y cierra SU sesión;
la rendición del cobrador queda para cuando el cobrador cobre; un gasto lo confirma quien tenga el permiso.

- `Caja`: la ventanilla o punto físico (maestro con `Code`).
- `SesionCaja`: un turno de un cajero en una caja: saldo inicial en efectivo, movimientos, cierre con lo declarado
  por forma de pago y las diferencias. Una sesión cerrada no se modifica.
- `MovimientoCaja`: cada ingreso o egreso, SIEMPRE con su origen (cobro, gasto o la reversión de uno de ellos). No se
  carga un ingreso «a mano» que duplique un cobro. Una reversión es un movimiento nuevo que apunta al original.
- `Gasto` (+ adjuntos y boleta interna): referencial, no es contabilidad ni compras. Solo un gasto CONFIRMADO genera
  su egreso, una única vez.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from comun.codigos import campo_code
from comun.modelos import ModeloInstitucional

IMPORTE = {'max_digits': 18, 'decimal_places': 2}


class Caja(ModeloInstitucional):
    Code = campo_code()
    nombre = models.CharField('nombre', max_length=80)
    activa = models.BooleanField('activa', default=True)

    class Meta:
        verbose_name = 'caja'
        verbose_name_plural = 'cajas'
        ordering = ['Code']
        constraints = [models.UniqueConstraint(fields=['institucion', 'Code'], name='caja_code_unico')]

    def __str__(self):
        return f'{self.Code} · {self.nombre}'


class SesionCaja(ModeloInstitucional):
    class Estado(models.TextChoices):
        ABIERTA = 'abierta', 'Abierta'
        EN_REVISION = 'en_revision', 'En revisión (con diferencias)'
        CERRADA = 'cerrada', 'Cerrada'

    referencia = models.CharField('referencia', max_length=12)
    caja = models.ForeignKey(Caja, on_delete=models.PROTECT, related_name='sesiones', verbose_name='caja')
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+',
                                    verbose_name='responsable')
    abierta_en = models.DateTimeField('abierta el')
    saldo_inicial = models.DecimalField('saldo inicial en efectivo', **IMPORTE)
    forma_inicial = models.ForeignKey('cobranzas.FormaPago', on_delete=models.PROTECT, null=True, blank=True,
                                      related_name='+', verbose_name='forma de pago del saldo inicial',
                                      help_text='Se fija al abrir: el arqueo de una sesión vieja no cambia si después '
                                                'se reordenan o desactivan las formas de pago.')
    estado = models.CharField('estado', max_length=12, choices=Estado.choices, default=Estado.ABIERTA, db_index=True)
    cerrada_en = models.DateTimeField('cerrada el', null=True, blank=True)
    observaciones_cierre = models.TextField('observaciones del cierre', blank=True)
    revisada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='+', verbose_name='revisada por')
    revisada_en = models.DateTimeField('revisada el', null=True, blank=True)
    comentario_revision = models.TextField('comentario de la revisión', blank=True)

    class Meta:
        verbose_name = 'sesión de caja'
        verbose_name_plural = 'sesiones de caja'
        ordering = ['-abierta_en']
        constraints = [
            models.UniqueConstraint(fields=['institucion', 'referencia'], name='sesion_referencia_unica'),
            # Un cajero tiene a lo sumo UNA sesión abierta, y una caja también.
            models.UniqueConstraint(fields=['responsable'], condition=Q(estado='abierta'), name='una_sesion_por_cajero'),
            models.UniqueConstraint(fields=['caja'], condition=Q(estado='abierta'), name='una_sesion_por_caja'),
            models.CheckConstraint(condition=Q(saldo_inicial__gte=0), name='sesion_saldo_inicial_no_negativo'),
        ]

    def __str__(self):
        return f'{self.referencia} · {self.caja.Code}'


class MovimientoCaja(ModeloInstitucional):
    class Tipo(models.TextChoices):
        INGRESO = 'ingreso', 'Ingreso'
        EGRESO = 'egreso', 'Egreso'

    class Origen(models.TextChoices):
        COBRO = 'cobro', 'Cobro'
        REVERSION_COBRO = 'reversion_cobro', 'Reversión de un cobro'
        GASTO = 'gasto', 'Gasto'
        REVERSION_GASTO = 'reversion_gasto', 'Reversión de un gasto'

    sesion = models.ForeignKey(SesionCaja, on_delete=models.PROTECT, related_name='movimientos', verbose_name='sesión')
    tipo = models.CharField('tipo', max_length=8, choices=Tipo.choices)
    origen = models.CharField('origen', max_length=16, choices=Origen.choices)
    forma_pago = models.ForeignKey('cobranzas.FormaPago', on_delete=models.PROTECT, related_name='+',
                                   verbose_name='forma de pago')
    importe = models.DecimalField('importe', **IMPORTE)
    descripcion = models.CharField('descripción', max_length=200)
    pago = models.ForeignKey('cobranzas.Pago', on_delete=models.PROTECT, null=True, blank=True,
                             related_name='movimientos_caja', verbose_name='pago')
    gasto = models.ForeignKey('caja.Gasto', on_delete=models.PROTECT, null=True, blank=True,
                              related_name='movimientos_caja', verbose_name='gasto')
    original = models.OneToOneField('self', on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='reversion', verbose_name='movimiento que revierte')
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                related_name='+', verbose_name='usuario')
    fecha_hora = models.DateTimeField('fecha y hora')

    class Meta:
        verbose_name = 'movimiento de caja'
        verbose_name_plural = 'movimientos de caja'
        ordering = ['fecha_hora', 'pk']
        constraints = [
            models.CheckConstraint(condition=Q(importe__gt=0), name='movimiento_importe_positivo'),
            # Cada cobro y cada gasto se reflejan UNA sola vez (un reintento no duplica).
            models.UniqueConstraint(fields=['pago'], condition=Q(origen='cobro'), name='un_ingreso_por_pago'),
            models.UniqueConstraint(fields=['gasto'], condition=Q(origen='gasto'), name='un_egreso_por_gasto'),
        ]


class DeclaracionCierre(ModeloInstitucional):
    """Al cerrar: lo que el cajero contó por forma de pago frente a lo que el sistema esperaba."""

    sesion = models.ForeignKey(SesionCaja, on_delete=models.PROTECT, related_name='declaraciones', verbose_name='sesión')
    forma_pago = models.ForeignKey('cobranzas.FormaPago', on_delete=models.PROTECT, related_name='+',
                                   verbose_name='forma de pago')
    esperado = models.DecimalField('esperado', **IMPORTE)
    declarado = models.DecimalField('declarado', **IMPORTE)
    diferencia = models.DecimalField('diferencia (declarado − esperado)', **IMPORTE)

    class Meta:
        verbose_name = 'declaración de cierre'
        verbose_name_plural = 'declaraciones de cierre'
        constraints = [models.UniqueConstraint(fields=['sesion', 'forma_pago'], name='declaracion_unica')]


class CategoriaGasto(ModeloInstitucional):
    Code = campo_code()
    nombre = models.CharField('nombre', max_length=80)
    activa = models.BooleanField('activa', default=True)

    class Meta:
        verbose_name = 'categoría de gasto'
        verbose_name_plural = 'categorías de gastos'
        ordering = ['nombre']
        constraints = [models.UniqueConstraint(fields=['institucion', 'Code'], name='categoria_gasto_code_unico')]

    def __str__(self):
        return self.nombre


CATEGORIAS_INICIALES = [('MANTENIMIENTO', 'Mantenimiento y reparaciones'), ('MATERIALES', 'Materiales'),
                        ('COMBUSTIBLE', 'Combustible'), ('SERVICIOS', 'Servicios (energía, internet…)'),
                        ('JORNALES', 'Jornales y honorarios'), ('OTROS', 'Otros')]


class Gasto(ModeloInstitucional):
    class Estado(models.TextChoices):
        REGISTRADO = 'registrado', 'Registrado (sin confirmar)'
        CONFIRMADO = 'confirmado', 'Confirmado'
        ANULADO = 'anulado', 'Anulado'

    referencia = models.CharField('referencia', max_length=12)
    fecha = models.DateField('fecha')
    motivo = models.CharField('motivo', max_length=200)
    importe = models.DecimalField('importe', **IMPORTE)
    categoria = models.ForeignKey(CategoriaGasto, on_delete=models.PROTECT, related_name='gastos',
                                  verbose_name='categoría')
    forma_pago = models.ForeignKey('cobranzas.FormaPago', on_delete=models.PROTECT, related_name='+',
                                   verbose_name='forma de pago')
    numero_comprobante = models.CharField('número de comprobante', max_length=60, blank=True)
    beneficiario = models.CharField('beneficiario', max_length=150)
    responsable = models.CharField('responsable', max_length=150, blank=True)
    sesion = models.ForeignKey(SesionCaja, on_delete=models.PROTECT, null=True, blank=True, related_name='gastos',
                               verbose_name='sesión de caja')
    estado = models.CharField('estado', max_length=12, choices=Estado.choices, default=Estado.REGISTRADO,
                              db_index=True)
    observaciones = models.TextField('observaciones', blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+',
                                       verbose_name='registrado por')
    confirmado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                       related_name='+', verbose_name='confirmado por')
    confirmado_en = models.DateTimeField('confirmado el', null=True, blank=True)
    anulado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='+', verbose_name='anulado por')
    anulado_en = models.DateTimeField('anulado el', null=True, blank=True)
    motivo_anulacion = models.TextField('motivo de la anulación', blank=True)

    class Meta:
        verbose_name = 'gasto'
        verbose_name_plural = 'gastos'
        ordering = ['-fecha', '-creado_en']
        constraints = [
            models.UniqueConstraint(fields=['institucion', 'referencia'], name='gasto_referencia_unica'),
            models.CheckConstraint(condition=Q(importe__gt=0), name='gasto_importe_positivo'),
        ]

    def __str__(self):
        return f'{self.referencia} · {self.motivo}'


class AdjuntoGasto(ModeloInstitucional):
    class Tipo(models.TextChoices):
        COMPROBANTE = 'comprobante', 'Comprobante (factura, ticket…)'
        BOLETA_FIRMADA = 'boleta_firmada', 'Boleta interna firmada'

    gasto = models.ForeignKey(Gasto, on_delete=models.PROTECT, related_name='adjuntos', verbose_name='gasto')
    tipo = models.CharField('tipo', max_length=15, choices=Tipo.choices)
    archivo = models.CharField('archivo privado', max_length=255)
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+',
                                   verbose_name='subido por')

    class Meta:
        verbose_name = 'adjunto de gasto'
        verbose_name_plural = 'adjuntos de gastos'
        ordering = ['pk']


class BoletaGasto(ModeloInstitucional):
    """Boleta interna para imprimir y firmar cuando el gasto no tiene comprobante. Evidencia administrativa:
    NO sustituye a un comprobante fiscal."""

    gasto = models.OneToOneField(Gasto, on_delete=models.PROTECT, related_name='boleta', verbose_name='gasto')
    numero = models.PositiveIntegerField('número interno')
    fecha = models.DateField('fecha')
    importe = models.DecimalField('importe', **IMPORTE)
    motivo = models.CharField('motivo', max_length=200)
    beneficiario = models.CharField('beneficiario', max_length=150)
    responsable = models.CharField('responsable', max_length=150, blank=True)

    class Meta:
        verbose_name = 'boleta interna de gasto'
        verbose_name_plural = 'boletas internas de gastos'
        constraints = [models.UniqueConstraint(fields=['institucion', 'numero'], name='boleta_numero_unico')]

    @property
    def numero_impreso(self) -> str:
        return f'{self.numero:07d}'
