"""
Numeración de los documentos de formulario continuo (facturas y notas de crédito).

Convención del proyecto (20/10/2026):
- Cada documento de formulario continuo lleva `SerNr`: su número, tomado del rango de numeración que la
  institución configuró para ESE punto de expedición y ESE tipo de documento.
- Una institución puede tener dos o más puntos de expedición (establecimiento + punto, ej. 001-001 y
  001-002); cada uno con sus propios rangos por tipo de documento.
- El contador del rango (`ultimo_usado`) es interno: nunca se muestra ni se acepta desde la interfaz.
  Lo avanza solo `servicios.tomar_sernr`, dentro de una transacción con bloqueo de fila.

Los documentos en sí (facturas, notas de crédito) llegan en la Fase 5 y heredan de `DocumentoNumerado`.
Nada se borra: puntos y rangos se desactivan.
"""
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q

from comun.codigos import campo_code
from comun.modelos import ModeloInstitucional

TRES_DIGITOS = RegexValidator(r'^\d{3}$', 'Use tres dígitos (ej. 001).')
DIGITOS_SERNR = 7  # 001-001-0000001


class TipoDocumento(models.TextChoices):
    FACTURA = 'factura', 'Factura'
    NOTA_CREDITO = 'nota_credito', 'Nota de crédito'


class PuntoExpedicion(ModeloInstitucional):
    Code = campo_code('código del punto')
    establecimiento = models.CharField('establecimiento', max_length=3, validators=[TRES_DIGITOS])
    punto = models.CharField('punto de expedición', max_length=3, validators=[TRES_DIGITOS])
    nombre = models.CharField('nombre', max_length=120, help_text='Ej. «Oficina central», «Caja móvil».')
    direccion = models.CharField('dirección', max_length=255, blank=True)
    activo = models.BooleanField('activo', default=True)
    observaciones = models.TextField('observaciones', blank=True)

    class Meta:
        verbose_name = 'punto de expedición'
        verbose_name_plural = 'puntos de expedición'
        ordering = ['establecimiento', 'punto']
        constraints = [
            models.UniqueConstraint(fields=['institucion', 'Code'], name='punto_expedicion_code_unico'),
            models.UniqueConstraint(fields=['institucion', 'establecimiento', 'punto'],
                                    name='punto_expedicion_numero_unico'),
        ]

    def __str__(self):
        return f'{self.prefijo} · {self.nombre}'

    @property
    def prefijo(self) -> str:
        return f'{self.establecimiento}-{self.punto}'


class RangoNumeracion(ModeloInstitucional):
    """Rango «desde–hasta» habilitado para un tipo de documento en un punto de expedición."""

    Code = campo_code('código del rango')
    punto = models.ForeignKey(PuntoExpedicion, on_delete=models.PROTECT, related_name='rangos',
                              verbose_name='punto de expedición')
    tipo_documento = models.CharField('tipo de documento', max_length=14, choices=TipoDocumento.choices)
    timbrado = models.CharField('timbrado', max_length=20, blank=True,
                                help_text='Número de timbrado habilitado, si corresponde.')
    desde = models.PositiveBigIntegerField('desde el número')
    hasta = models.PositiveBigIntegerField('hasta el número')
    vigencia_desde = models.DateField('vigente desde', null=True, blank=True)
    vigencia_hasta = models.DateField('vigente hasta', null=True, blank=True)
    activo = models.BooleanField('activo', default=True)
    observaciones = models.TextField('observaciones', blank=True)
    # Contador interno: último SerNr entregado. Nunca se expone (convención del proyecto).
    ultimo_usado = models.PositiveBigIntegerField('último número usado (interno)', null=True, blank=True,
                                                  editable=False)

    class Meta:
        verbose_name = 'rango de numeración'
        verbose_name_plural = 'rangos de numeración'
        ordering = ['punto__establecimiento', 'punto__punto', 'tipo_documento', 'desde']
        constraints = [
            models.UniqueConstraint(fields=['institucion', 'Code'], name='rango_code_unico'),
            models.CheckConstraint(condition=Q(desde__gte=1), name='rango_desde_positivo'),
            models.CheckConstraint(condition=Q(hasta__gte=F('desde')), name='rango_hasta_mayor_igual'),
            models.CheckConstraint(
                condition=Q(ultimo_usado__isnull=True) | (Q(ultimo_usado__gte=F('desde')) & Q(ultimo_usado__lte=F('hasta'))),
                name='rango_ultimo_dentro',
            ),
            models.CheckConstraint(
                condition=Q(vigencia_desde__isnull=True) | Q(vigencia_hasta__isnull=True)
                | Q(vigencia_hasta__gte=F('vigencia_desde')),
                name='rango_vigencia_ordenada',
            ),
        ]

    def __str__(self):
        return f'{self.Code} · {self.punto.prefijo} {self.get_tipo_documento_display()} {self.desde}-{self.hasta}'

    @property
    def en_uso(self) -> bool:
        return self.ultimo_usado is not None

    @property
    def agotado(self) -> bool:
        return self.ultimo_usado is not None and self.ultimo_usado >= self.hasta


class DocumentoNumerado(ModeloInstitucional):
    """
    Base de los documentos de formulario continuo (Fase 5). `SerNr` es único por institución, punto de
    expedición, tipo de documento y timbrado (con un timbrado nuevo la numeración puede volver a empezar).
    """

    TIPO_DOCUMENTO = ''  # cada documento concreto declara el suyo (TipoDocumento)

    punto = models.ForeignKey(PuntoExpedicion, on_delete=models.PROTECT, related_name='+',
                              verbose_name='punto de expedición')
    timbrado = models.CharField('timbrado', max_length=20, blank=True)
    SerNr = models.PositiveBigIntegerField('número (SerNr)')

    class Meta:
        abstract = True
        constraints = [
            models.UniqueConstraint(fields=['institucion', 'punto', 'timbrado', 'SerNr'],
                                    name='%(app_label)s_%(class)s_sernr_unico'),
        ]

    @property
    def numero_impreso(self) -> str:
        return formatear_sernr(self.punto, self.SerNr)


def formatear_sernr(punto: PuntoExpedicion, sernr: int) -> str:
    """Número como se imprime: 001-001-0000123."""
    return f'{punto.prefijo}-{sernr:0{DIGITOS_SERNR}d}'


# --- Facturas (Fase 5) ---------------------------------------------------------------------------------

IMPORTE = {'max_digits': 18, 'decimal_places': 2}


class Factura(DocumentoNumerado):
    """
    Factura de venta (sección 11). Se emite cuando el usuario viene a pagar (decisión 21/10/2026): incluye una o
    más liquidaciones de las conexiones del cliente, cada liquidación entera y en una sola factura. Si el usuario
    quiere pagar en partes, la factura se emite a crédito y se paga después con varios recibos (Fase 6).
    Nada se borra: una factura se anula con motivo y sus liquidaciones vuelven a quedar para facturar.
    """

    TIPO_DOCUMENTO = TipoDocumento.FACTURA

    class Modalidad(models.TextChoices):
        AUTOIMPRESA = 'autoimpresa', 'Autoimpresa'
        ELECTRONICA = 'electronica', 'Electrónica'

    class Condicion(models.TextChoices):
        CONTADO = 'contado', 'Contado'
        CREDITO = 'credito', 'Crédito'

    class Estado(models.TextChoices):
        EN_TRAMITE = 'en_tramite', 'En trámite con el proveedor electrónico'
        EMITIDA = 'emitida', 'Emitida'
        RECHAZADA = 'rechazada', 'Rechazada por el proveedor'
        ANULADA = 'anulada', 'Anulada'

    referencia = models.CharField('referencia', max_length=12,
                                  help_text='Clave interna visible (F-XXXXXXXX); el número fiscal es establecimiento-punto-SerNr.')
    modalidad = models.CharField('modalidad', max_length=12, choices=Modalidad.choices)
    rango = models.ForeignKey(RangoNumeracion, on_delete=models.PROTECT, related_name='facturas',
                              verbose_name='rango de numeración')
    timbrado_vigencia_desde = models.DateField('timbrado vigente desde', null=True, blank=True)
    timbrado_vigencia_hasta = models.DateField('timbrado vigente hasta', null=True, blank=True)
    cliente = models.ForeignKey('padron.Cliente', on_delete=models.PROTECT, related_name='facturas',
                                verbose_name='cliente')
    # Instantánea del cliente al emitir (si después cambia su nombre o documento, la factura no cambia).
    cliente_nombre = models.CharField('nombre o razón social', max_length=200)
    cliente_documento = models.CharField('RUC o documento', max_length=30, blank=True)
    cliente_direccion = models.CharField('dirección', max_length=255, blank=True)
    condicion = models.CharField('condición de venta', max_length=8, choices=Condicion.choices)
    fecha_emision = models.DateField('fecha de emisión')
    fecha_vencimiento = models.DateField('fecha de vencimiento', null=True, blank=True)
    subtotal_exento = models.DecimalField('total exentas', **IMPORTE)
    subtotal_iva5 = models.DecimalField('total gravadas 5 % (IVA incluido)', **IMPORTE)
    subtotal_iva10 = models.DecimalField('total gravadas 10 % (IVA incluido)', **IMPORTE)
    iva5 = models.DecimalField('liquidación IVA 5 %', **IMPORTE)
    iva10 = models.DecimalField('liquidación IVA 10 %', **IMPORTE)
    total = models.DecimalField('total a pagar', **IMPORTE)
    estado = models.CharField('estado', max_length=12, choices=Estado.choices, db_index=True)
    observaciones = models.TextField('observaciones', blank=True)
    cdc = models.CharField('CDC (electrónica)', max_length=64, blank=True)
    datos_fiscales = models.JSONField('datos devueltos por el proveedor', default=dict, blank=True)
    emitida_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+',
                                    verbose_name='emitida por')
    anulada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='+', verbose_name='anulada por')
    anulada_en = models.DateTimeField('anulada el', null=True, blank=True)
    motivo_anulacion = models.TextField('motivo de la anulación', blank=True)

    class Meta(DocumentoNumerado.Meta):
        verbose_name = 'factura'
        verbose_name_plural = 'facturas'
        ordering = ['-fecha_emision', '-SerNr']
        constraints = DocumentoNumerado.Meta.constraints + [
            models.UniqueConstraint(fields=['institucion', 'referencia'], name='factura_referencia_unica'),
            models.CheckConstraint(condition=~Q(condicion='credito') | Q(fecha_vencimiento__isnull=False),
                                   name='credito_con_vencimiento'),
        ]

    def __str__(self):
        return f'{self.numero_impreso} · {self.cliente_nombre}'


class LineaFactura(ModeloInstitucional):
    """Una línea por concepto de cada liquidación. Importe sin IVA + su parte del IVA = importe de la columna."""

    factura = models.ForeignKey(Factura, on_delete=models.PROTECT, related_name='lineas', verbose_name='factura')
    orden = models.PositiveSmallIntegerField('orden', default=0)
    liquidacion = models.ForeignKey('tarifas.Liquidacion', on_delete=models.PROTECT, related_name='lineas_factura',
                                    verbose_name='liquidación')
    descripcion = models.CharField('descripción', max_length=200)
    tipo = models.CharField('tipo de concepto', max_length=12)
    cantidad = models.DecimalField('cantidad', max_digits=20, decimal_places=3)
    precio_unitario = models.DecimalField('precio unitario (sin IVA)', max_digits=18, decimal_places=3)
    iva = models.CharField('IVA', max_length=6)
    importe = models.DecimalField('importe sin IVA', **IMPORTE)
    importe_iva = models.DecimalField('IVA de la línea', **IMPORTE)
    total_linea = models.DecimalField('importe con IVA', **IMPORTE)

    class Meta:
        verbose_name = 'línea de factura'
        verbose_name_plural = 'líneas de factura'
        ordering = ['orden', 'id']


class AsignacionFacturaLiquidacion(ModeloInstitucional):
    """Qué liquidación se facturó en qué factura (InvoiceReadingAllocation). Una vigente por liquidación."""

    class Estado(models.TextChoices):
        VIGENTE = 'vigente', 'Vigente'
        ANULADA = 'anulada', 'Anulada (la factura se anuló o fue rechazada)'

    factura = models.ForeignKey(Factura, on_delete=models.PROTECT, related_name='asignaciones', verbose_name='factura')
    liquidacion = models.ForeignKey('tarifas.Liquidacion', on_delete=models.PROTECT, related_name='asignaciones',
                                    verbose_name='liquidación')
    importe = models.DecimalField('importe aplicado', **IMPORTE)
    estado = models.CharField('estado', max_length=8, choices=Estado.choices, default=Estado.VIGENTE)

    class Meta:
        verbose_name = 'liquidación facturada'
        verbose_name_plural = 'liquidaciones facturadas'
        constraints = [
            # Una liquidación no se factura dos veces (prueba obligatoria 8).
            models.UniqueConstraint(fields=['liquidacion'], condition=Q(estado='vigente'),
                                    name='liquidacion_facturada_una_vez'),
        ]


# --- Factura electrónica: capa de integración (sección 11.2) ------------------------------------------

class ProveedorFacturacion(ModeloInstitucional):
    """
    Proveedor de factura electrónica de una institución. Lo configura la plataforma (admin): qué adaptador usar,
    ambiente y credenciales (cifradas). Sin adaptador implementado no se emite: no se inventan APIs (D35).
    """

    class Ambiente(models.TextChoices):
        PRUEBAS = 'pruebas', 'Pruebas'
        PRODUCCION = 'produccion', 'Producción'

    nombre = models.CharField('proveedor', max_length=120)
    adaptador = models.CharField('adaptador', max_length=40,
                                 help_text='Código del adaptador programado para este proveedor.')
    ambiente = models.CharField('ambiente', max_length=10, choices=Ambiente.choices, default=Ambiente.PRUEBAS)
    credenciales = models.TextField('credenciales (cifradas)', blank=True, editable=False)
    activo = models.BooleanField('activo', default=True)

    class Meta:
        verbose_name = 'proveedor de factura electrónica'
        verbose_name_plural = 'proveedores de factura electrónica'
        constraints = [models.UniqueConstraint(fields=['institucion'], condition=Q(activo=True),
                                               name='un_proveedor_activo')]

    def __str__(self):
        return f'{self.nombre} ({self.get_ambiente_display()})'


class SolicitudElectronica(ModeloInstitucional):
    """ExternalInvoiceRequest: una por factura electrónica, con su identificador único (idempotencia)."""

    class Estado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente de envío'
        ENVIADA = 'enviada', 'Enviada'
        EN_PROCESO = 'en_proceso', 'En procesamiento'
        APROBADA = 'aprobada', 'Emitida y confirmada'
        RECHAZADA = 'rechazada', 'Rechazada'
        ERROR = 'error_recuperable', 'Error recuperable'
        DESCONOCIDO = 'desconocido', 'Estado desconocido, pendiente de consulta'
        ANULADA = 'anulada', 'Anulada'

    factura = models.OneToOneField(Factura, on_delete=models.PROTECT, related_name='solicitud', verbose_name='factura')
    proveedor = models.ForeignKey(ProveedorFacturacion, on_delete=models.PROTECT, related_name='solicitudes',
                                  verbose_name='proveedor')
    id_solicitud = models.UUIDField('identificador único de la solicitud', unique=True)
    estado = models.CharField('estado', max_length=18, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    intentos = models.PositiveSmallIntegerField('intentos', default=0)
    numero_proveedor = models.CharField('identificador del proveedor', max_length=120, blank=True)
    ultima_respuesta = models.JSONField('última respuesta', default=dict, blank=True)
    ultimo_error = models.TextField('último error', blank=True)

    class Meta:
        verbose_name = 'solicitud de factura electrónica'
        verbose_name_plural = 'solicitudes de factura electrónica'


class RegistroIntegracion(ModeloInstitucional):
    """IntegrationLog: cada llamada al proveedor y cada cambio de estado, antes y después."""

    solicitud = models.ForeignKey(SolicitudElectronica, on_delete=models.PROTECT, related_name='registros',
                                  verbose_name='solicitud')
    operacion = models.CharField('operación', max_length=20)  # enviar, consultar, anular
    estado_antes = models.CharField('estado antes', max_length=18)
    estado_despues = models.CharField('estado después', max_length=18, blank=True)
    detalle = models.JSONField('detalle (sin credenciales)', default=dict, blank=True)
    error = models.TextField('error', blank=True)

    class Meta:
        verbose_name = 'registro de integración'
        verbose_name_plural = 'registros de integración'
        ordering = ['creado_en', 'id']
