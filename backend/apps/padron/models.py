"""
Padrón de cada institución: clientes (titulares), conexiones de agua, medidores e instalaciones.

Decisiones (20/10/2026):
- Un cliente puede tener VARIAS conexiones.
- Una conexión tiene UN medidor vigente a la vez; al sustituirlo, el anterior queda en el historial con
  su lectura de retiro (las lecturas históricas siguen apuntando a la instalación de ese momento).
- El medidor físico (`Medidor`) está separado de su instalación en una conexión (`InstalacionMedidor`).

Nada se borra: clientes y conexiones se archivan; las instalaciones se cierran con fecha de retiro.
"""
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from comun.codigos import campo_code
from comun.modelos import ModeloInstitucional

DECIMALES_LECTURA = 3  # m³ con tres decimales (litros). Se ajusta por unidad de medidor si hiciera falta.


class Cliente(ModeloInstitucional):
    class TipoPersona(models.TextChoices):
        FISICA = 'fisica', 'Persona física'
        JURIDICA = 'juridica', 'Persona jurídica'

    class Estado(models.TextChoices):
        ACTIVO = 'activo', 'Activo'
        INACTIVO = 'inactivo', 'Inactivo'
        ARCHIVADO = 'archivado', 'Archivado'

    Code = campo_code('código de cliente')
    nombre = models.CharField('nombre completo o razón social', max_length=200)
    tipo_persona = models.CharField('tipo de persona', max_length=10, choices=TipoPersona.choices,
                                    default=TipoPersona.FISICA)
    documento = models.CharField('documento de identidad o RUC', max_length=30, blank=True,
                                 help_text='No es la clave del cliente: puede faltar o repetirse.')
    telefono = models.CharField('teléfono', max_length=50, blank=True)
    correo = models.EmailField('correo electrónico', blank=True)
    documento_normalizado = models.CharField(
        'documento normalizado', max_length=30, blank=True, editable=False, db_index=True,
        help_text='Sin puntos ni guiones (el RUC sin su dígito verificador): reconoce a la misma persona en todas '
                  'las instituciones (portal de abonados).')
    direccion_referencia = models.CharField('dirección de referencia', max_length=255, blank=True)
    observaciones = models.TextField('observaciones', blank=True)
    estado = models.CharField('estado', max_length=10, choices=Estado.choices, default=Estado.ACTIVO, db_index=True)
    fecha_alta = models.DateField('fecha de alta')

    class Meta:
        verbose_name = 'cliente'
        verbose_name_plural = 'clientes'
        ordering = ['nombre']
        constraints = [models.UniqueConstraint(fields=['institucion', 'Code'], name='cliente_code_unico')]
        indexes = [models.Index(fields=['institucion', 'documento']), models.Index(fields=['institucion', 'nombre'])]

    def save(self, *args, **kwargs):
        from comun.documentos import normalizar_documento
        self.documento_normalizado = normalizar_documento(self.documento)
        if kwargs.get('update_fields') is not None and 'documento' in kwargs['update_fields']:
            kwargs['update_fields'] = {*kwargs['update_fields'], 'documento_normalizado'}
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.Code} · {self.nombre}'


class Conexion(ModeloInstitucional):
    class Estado(models.TextChoices):
        EN_INSTALACION = 'en_instalacion', 'En instalación'
        PENDIENTE_UBICACION = 'pendiente_ubicacion', 'Pendiente de ubicación'
        ACTIVA = 'activa', 'Activa'
        SUSPENDIDA = 'suspendida', 'Suspendida'
        DESCONECTADA = 'desconectada', 'Desconectada'
        ARCHIVADA = 'archivada', 'Archivada'

    class MetodoUbicacion(models.TextChoices):
        SIN_UBICACION = 'sin_ubicacion', 'Sin ubicación'
        GPS = 'gps', 'GPS del teléfono'
        MAPA = 'mapa', 'Marcada en el mapa'
        MANUAL = 'manual', 'Coordenadas cargadas a mano'

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='conexiones', verbose_name='titular')
    Code = campo_code('código de conexión')
    direccion = models.CharField('dirección', max_length=255, blank=True)
    barrio = models.ForeignKey('territorio.Barrio', null=True, blank=True, on_delete=models.PROTECT,
                               related_name='conexiones', verbose_name='barrio')
    latitud = models.DecimalField('latitud', max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField('longitud', max_digits=9, decimal_places=6, null=True, blank=True)
    metodo_ubicacion = models.CharField('método de geolocalización', max_length=14,
                                        choices=MetodoUbicacion.choices, default=MetodoUbicacion.SIN_UBICACION)
    precision_metros = models.PositiveIntegerField('precisión (m)', null=True, blank=True,
                                                   help_text='Precisión informada por el GPS, si se conoce.')
    foto_vivienda = models.CharField('foto de la vivienda (archivo privado)', max_length=255, blank=True)
    tarifa = models.ForeignKey('tarifas.Tarifa', null=True, blank=True, on_delete=models.PROTECT,
                               related_name='conexiones', verbose_name='tipo de conexión (tarifa)',
                               help_text='Vacío: se usa la tarifa por defecto de la institución.')
    estado = models.CharField('estado', max_length=20, choices=Estado.choices, default=Estado.EN_INSTALACION,
                              db_index=True)
    fecha_instalacion = models.DateField('fecha de instalación', null=True, blank=True)
    observaciones = models.TextField('observaciones', blank=True)

    class Meta:
        verbose_name = 'conexión'
        verbose_name_plural = 'conexiones'
        ordering = ['Code']
        constraints = [
            models.UniqueConstraint(fields=['institucion', 'Code'], name='conexion_code_unico'),
            models.CheckConstraint(
                condition=(Q(latitud__isnull=True) & Q(longitud__isnull=True))
                | (Q(latitud__isnull=False) & Q(longitud__isnull=False)),
                name='conexion_coordenadas_completas',
            ),
        ]

    def __str__(self):
        return f'{self.Code} · {self.direccion or self.cliente.nombre}'

    @property
    def tiene_ubicacion(self) -> bool:
        return self.latitud is not None and self.longitud is not None

    def instalacion_vigente(self):
        return self.instalaciones.filter(fecha_retiro__isnull=True).select_related('medidor').first()


class TitularidadConexion(ModeloInstitucional):
    """Historial de titulares de una conexión (el vigente tiene `hasta` vacío)."""

    conexion = models.ForeignKey(Conexion, on_delete=models.PROTECT, related_name='titularidades',
                                 verbose_name='conexión')
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='titularidades', verbose_name='cliente')
    desde = models.DateField('desde')
    hasta = models.DateField('hasta', null=True, blank=True)
    motivo = models.CharField('motivo del cambio', max_length=255, blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='+',
                                       verbose_name='registrado por')

    class Meta:
        verbose_name = 'titularidad de conexión'
        verbose_name_plural = 'historial de titulares'
        ordering = ['-desde', '-id']
        constraints = [
            models.UniqueConstraint(fields=['conexion'], condition=Q(hasta__isnull=True), name='un_titular_vigente'),
        ]


def normalizar_numero_medidor(valor) -> str:
    """Número del medidor: sin espacios a los costados y en mayúsculas (se busca sin importar mayúsculas)."""
    return (valor or '').strip().upper()


def validar_numero_medidor(valor):
    if valor and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9./-]*', valor.strip()):
        raise ValidationError('Solo letras, números y los signos - . / (sin espacios).')


class Medidor(ModeloInstitucional):
    class Estado(models.TextChoices):
        DISPONIBLE = 'disponible', 'Disponible (en depósito)'
        INSTALADO = 'instalado', 'Instalado'
        RETIRADO = 'retirado', 'Retirado'
        DANADO = 'danado', 'Dañado'
        BAJA = 'baja', 'Dado de baja'

    Code = campo_code('código (identificación interna)')
    numero = models.CharField(
        'número del medidor', max_length=40, blank=True, db_index=True, validators=[validar_numero_medidor],
        help_text='El número grabado en el medidor (letras y números). El cobrador lo busca por este número.',
    )
    marca = models.CharField('marca', max_length=60, blank=True)
    modelo = models.CharField('modelo', max_length=60, blank=True)
    unidad = models.CharField('unidad de lectura', max_length=10, default='m3')
    lectura_maxima = models.DecimalField(
        'lectura máxima antes de volver a cero', max_digits=12, decimal_places=DECIMALES_LECTURA, null=True, blank=True,
        help_text='Capacidad del contador (ej. 99999). Sirve para detectar reinicios en las lecturas.',
    )
    estado = models.CharField('estado', max_length=10, choices=Estado.choices, default=Estado.DISPONIBLE, db_index=True)
    observaciones = models.TextField('observaciones', blank=True)

    class Meta:
        verbose_name = 'medidor'
        verbose_name_plural = 'medidores'
        ordering = ['Code']
        constraints = [
            models.UniqueConstraint(fields=['institucion', 'Code'], name='medidor_code_unico'),
            models.UniqueConstraint(fields=['institucion', 'numero'], condition=~Q(numero=''),
                                    name='medidor_numero_unico'),
        ]

    def __str__(self):
        return self.Code

    def save(self, *args, **kwargs):
        self.numero = normalizar_numero_medidor(self.numero)
        super().save(*args, **kwargs)


class InstalacionMedidor(ModeloInstitucional):
    """
    Un medidor instalado en una conexión durante un período. Las lecturas (Fase 3) apuntan a la
    instalación, así conservan el medidor correcto aunque después se sustituya.
    """

    conexion = models.ForeignKey(Conexion, on_delete=models.PROTECT, related_name='instalaciones',
                                 verbose_name='conexión')
    medidor = models.ForeignKey(Medidor, on_delete=models.PROTECT, related_name='instalaciones', verbose_name='medidor')
    fecha_instalacion = models.DateField('fecha de instalación')
    lectura_inicial = models.DecimalField('lectura inicial', max_digits=12, decimal_places=DECIMALES_LECTURA)
    fecha_retiro = models.DateField('fecha de retiro', null=True, blank=True)
    lectura_retiro = models.DecimalField('lectura al retirar', max_digits=12, decimal_places=DECIMALES_LECTURA,
                                         null=True, blank=True)
    motivo_retiro = models.CharField('motivo del retiro o sustitución', max_length=255, blank=True)
    instalado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='+',
                                      verbose_name='responsable de la instalación')
    retirado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                     related_name='+', verbose_name='responsable del retiro')
    observaciones = models.TextField('observaciones', blank=True)

    class Meta:
        verbose_name = 'instalación de medidor'
        verbose_name_plural = 'instalaciones de medidores'
        ordering = ['-fecha_instalacion', '-id']
        constraints = [
            # Un medidor no puede estar instalado en dos conexiones a la vez…
            models.UniqueConstraint(fields=['medidor'], condition=Q(fecha_retiro__isnull=True),
                                    name='medidor_una_instalacion_vigente'),
            # …ni una conexión tener dos medidores vigentes (decisión 20/10/2026).
            models.UniqueConstraint(fields=['conexion'], condition=Q(fecha_retiro__isnull=True),
                                    name='conexion_un_medidor_vigente'),
            models.CheckConstraint(condition=Q(fecha_retiro__isnull=True) | Q(fecha_retiro__gte=F('fecha_instalacion')),
                                   name='retiro_posterior_a_instalacion'),
            models.CheckConstraint(condition=Q(lectura_inicial__gte=0), name='lectura_inicial_no_negativa'),
            models.CheckConstraint(
                condition=(Q(fecha_retiro__isnull=True) & Q(lectura_retiro__isnull=True))
                | (Q(fecha_retiro__isnull=False) & Q(lectura_retiro__isnull=False)),
                name='retiro_con_lectura',
            ),
        ]

    def __str__(self):
        return f'{self.medidor} en {self.conexion.Code} desde {self.fecha_instalacion:%d/%m/%Y}'

    @property
    def vigente(self) -> bool:
        return self.fecha_retiro is None
