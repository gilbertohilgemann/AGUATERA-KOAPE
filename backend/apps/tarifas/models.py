"""
Tarifas y liquidaciones (sección 9.3).

- Una TARIFA es el cuadro tarifario de un tipo de conexión (Residencial, Comercial, Social…); cada conexión tiene
  la suya y las que no tienen usan la tarifa «por defecto» de la institución.
- Cada tarifa tiene VERSIONES por vigencia (desde un período AAAA-MM). Una versión ya usada en una liquidación no
  se modifica: para cambiar precios se crea otra versión. Así las liquidaciones históricas no cambian.
- Cada versión tiene CONCEPTOS configurables (TariffRule): consumo mínimo, excedente, tramos, precio por m³, cargo
  fijo y porcentajes (ej. tasa ERSSAN), cada uno con su IVA (10 %, 5 % o exento). Los precios NO incluyen IVA.
- La LIQUIDACIÓN (ConsumptionSettlement) se genera al confirmarse una lectura y guarda una instantánea completa:
  conceptos y precios usados, consumo, líneas, subtotales por IVA y total. No se recalcula sola.

Importes en guaraníes, redondeados a enteros por línea (y el IVA por tasa).
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.recorridos.models import PERIODO
from comun.codigos import campo_code
from comun.modelos import ModeloInstitucional

IMPORTE = {'max_digits': 18, 'decimal_places': 2}
CANTIDAD = {'max_digits': 12, 'decimal_places': 3}
# Tope de importes: por encima, la liquidación no se genera (casi seguro una lectura mal tipeada) y queda sin liquidar.
IMPORTE_MAXIMO = 10 ** 15


class Iva(models.TextChoices):
    IVA10 = '10', 'IVA 10 %'
    IVA5 = '5', 'IVA 5 %'
    EXENTO = 'exento', 'Exento'


class Tarifa(ModeloInstitucional):
    Code = campo_code('código de la tarifa')
    nombre = models.CharField('tipo de conexión', max_length=120, help_text='Ej. Residencial, Comercial, Social.')
    descripcion = models.CharField('descripción', max_length=255, blank=True)
    por_defecto = models.BooleanField('por defecto', default=False,
                                      help_text='La usan las conexiones que no tienen una tarifa asignada.')
    activa = models.BooleanField('activa', default=True)

    class Meta:
        verbose_name = 'tarifa'
        verbose_name_plural = 'tarifas'
        ordering = ['nombre']
        constraints = [
            models.UniqueConstraint(fields=['institucion', 'Code'], name='tarifa_code_unico'),
            models.UniqueConstraint(fields=['institucion'], condition=Q(por_defecto=True), name='una_tarifa_por_defecto'),
        ]

    def __str__(self):
        return f'{self.Code} · {self.nombre}'


class VersionTarifa(ModeloInstitucional):
    tarifa = models.ForeignKey(Tarifa, on_delete=models.PROTECT, related_name='versiones', verbose_name='tarifa')
    vigente_desde = models.CharField('vigente desde el período', max_length=7, validators=[PERIODO])
    observaciones = models.TextField('observaciones', blank=True, help_text='Ej. resolución que la aprueba.')

    class Meta:
        verbose_name = 'versión de tarifa'
        verbose_name_plural = 'versiones de tarifas'
        ordering = ['-vigente_desde']
        constraints = [models.UniqueConstraint(fields=['tarifa', 'vigente_desde'], name='version_unica_por_periodo')]

    def __str__(self):
        return f'{self.tarifa.Code} desde {self.vigente_desde}'


class ConceptoTarifa(ModeloInstitucional):
    """Una regla de la tarifa (TariffRule)."""

    class Tipo(models.TextChoices):
        MINIMO = 'minimo', 'Consumo mínimo (se cobra se use o no)'
        EXCEDENTE = 'excedente', 'Excedente sobre el mínimo (por m³)'
        TRAMO = 'tramo', 'Tramo de consumo (por m³)'
        POR_M3 = 'por_m3', 'Precio por cada m³ consumido'
        FIJO = 'fijo', 'Cargo fijo mensual'
        PORCENTAJE = 'porcentaje', 'Porcentaje sobre el servicio (ej. tasa ERSSAN)'

    version = models.ForeignKey(VersionTarifa, on_delete=models.CASCADE, related_name='conceptos',
                                verbose_name='versión')
    orden = models.PositiveSmallIntegerField('orden', default=0)
    nombre = models.CharField('nombre en la factura', max_length=120)
    tipo = models.CharField('tipo', max_length=12, choices=Tipo.choices)
    cantidad = models.DecimalField('m³ del mínimo', **CANTIDAD, null=True, blank=True)
    desde = models.DecimalField('tramo desde (m³)', **CANTIDAD, null=True, blank=True)
    hasta = models.DecimalField('tramo hasta (m³)', **CANTIDAD, null=True, blank=True,
                                help_text='Vacío: sin límite.')
    precio = models.DecimalField('precio (por m³ o monto fijo)', **IMPORTE, null=True, blank=True)
    porcentaje = models.DecimalField('porcentaje', max_digits=6, decimal_places=3, null=True, blank=True)
    iva = models.CharField('IVA', max_length=6, choices=Iva.choices, default=Iva.IVA10)

    class Meta:
        verbose_name = 'concepto de tarifa'
        verbose_name_plural = 'conceptos de tarifa'
        ordering = ['orden', 'id']


class Liquidacion(ModeloInstitucional):
    """Importe de una lectura confirmada según la tarifa vigente en su período (ConsumptionSettlement)."""

    class Estado(models.TextChoices):
        VIGENTE = 'vigente', 'Vigente'
        ANULADA = 'anulada', 'Anulada'

    numero = models.CharField('número de liquidación', max_length=12)
    lectura = models.ForeignKey('lecturas.Lectura', on_delete=models.PROTECT, related_name='liquidaciones',
                                verbose_name='lectura')
    conexion = models.ForeignKey('padron.Conexion', on_delete=models.PROTECT, related_name='liquidaciones',
                                 verbose_name='conexión')
    periodo = models.CharField('período', max_length=7, db_index=True)
    tarifa = models.ForeignKey(Tarifa, on_delete=models.PROTECT, related_name='liquidaciones', verbose_name='tarifa')
    version = models.ForeignKey(VersionTarifa, on_delete=models.PROTECT, related_name='liquidaciones',
                                verbose_name='versión de la tarifa')
    parametros = models.JSONField('conceptos y precios usados (instantánea)')
    consumo = models.DecimalField('consumo liquidado (m³)', **CANTIDAD)
    subtotal_exento = models.DecimalField('subtotal exento', **IMPORTE)
    subtotal_iva5 = models.DecimalField('subtotal gravado 5 %', **IMPORTE)
    subtotal_iva10 = models.DecimalField('subtotal gravado 10 %', **IMPORTE)
    iva5 = models.DecimalField('IVA 5 %', **IMPORTE)
    iva10 = models.DecimalField('IVA 10 %', **IMPORTE)
    total = models.DecimalField('total', **IMPORTE)
    estado = models.CharField('estado', max_length=8, choices=Estado.choices, default=Estado.VIGENTE, db_index=True)
    motivo_anulacion = models.TextField('motivo de la anulación', blank=True)
    anulada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='+', verbose_name='anulada por')
    anulada_en = models.DateTimeField('anulada el', null=True, blank=True)

    class Meta:
        verbose_name = 'liquidación'
        verbose_name_plural = 'liquidaciones'
        ordering = ['-periodo', '-creado_en']
        constraints = [
            models.UniqueConstraint(fields=['institucion', 'numero'], name='liquidacion_numero_unico'),
            # Una sola liquidación vigente por lectura: no se liquida dos veces.
            models.UniqueConstraint(fields=['lectura'], condition=Q(estado='vigente'), name='una_liquidacion_vigente'),
        ]

    def __str__(self):
        return f'{self.numero} · {self.conexion.Code} {self.periodo}'


class LineaLiquidacion(ModeloInstitucional):
    liquidacion = models.ForeignKey(Liquidacion, on_delete=models.PROTECT, related_name='lineas',
                                    verbose_name='liquidación')
    orden = models.PositiveSmallIntegerField('orden', default=0)
    concepto = models.CharField('concepto', max_length=120)
    tipo = models.CharField('tipo', max_length=12, choices=ConceptoTarifa.Tipo.choices)
    # m³, 1 (cargo fijo) o la base en guaraníes de un porcentaje: por eso admite importes.
    cantidad = models.DecimalField('cantidad o base', max_digits=20, decimal_places=3)
    precio = models.DecimalField('precio unitario o porcentaje', max_digits=18, decimal_places=3)
    importe = models.DecimalField('importe (sin IVA)', **IMPORTE)
    iva = models.CharField('IVA', max_length=6, choices=Iva.choices)

    class Meta:
        verbose_name = 'línea de liquidación'
        verbose_name_plural = 'líneas de liquidación'
        ordering = ['orden', 'id']
