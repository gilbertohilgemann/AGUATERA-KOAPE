"""
Lecturas de medidores (sección 9). Módulo crítico.

- Cada lectura apunta a la INSTALACIÓN del medidor vigente al leer (y al medidor): aunque después se sustituya,
  conserva el medidor correcto.
- Guarda una instantánea de lo usado al registrarla: lectura y fecha anterior, consumo. No se recalcula sola.
- Llega del celular del cobrador con un `id_operacion` (UUID generado en el teléfono): reenviarla no la duplica.
- Foto principal y GPS son obligatorios (decisión 20/10/2026). La foto de galería solo si la institución lo permite.
- Lo dudoso no se rechaza ni se pisa: queda «Requiere revisión» (lectura menor que la anterior, duplicada,
  medidor sustituido o recorrido cerrado mientras estaba sin conexión) y la oficina la autoriza, corrige o anula.
- Una lectura no es una factura ni un recibo. Su clave visible es el código de comprobante (L-XXXXXXXX).
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from comun.modelos import ModeloInstitucional
from apps.padron.models import DECIMALES_LECTURA


class Lectura(ModeloInstitucional):
    class Estado(models.TextChoices):
        CONFIRMADA = 'confirmada', 'Confirmada'
        REVISION = 'requiere_revision', 'Requiere revisión'
        ANULADA = 'anulada', 'Anulada'

    class MotivoRevision(models.TextChoices):
        LECTURA_MENOR = 'lectura_menor', 'Lectura menor que la anterior'
        DUPLICADA = 'duplicada', 'Ya había una lectura confirmada en el período'
        MEDIDOR_CAMBIADO = 'medidor_cambiado', 'El medidor se sustituyó antes de sincronizar'
        RECORRIDO_CERRADO = 'recorrido_cerrado', 'El recorrido se cerró antes de sincronizar'
        ASIGNACION_RETIRADA = 'asignacion_retirada', 'Se retiró la asignación del cobrador antes de sincronizar'
        CORRECCION = 'correccion', 'Corrección pendiente de autorizar'
        POSTERIOR_EXISTENTE = 'posterior_existente', 'Ya hay una lectura de un período posterior'
        FUERA_DEL_RECORRIDO = 'fuera_del_recorrido', 'La conexión ya no está en el recorrido'
        FECHA_DUDOSA = 'fecha_dudosa', 'Fecha y hora del teléfono dudosa (futura)'
        GALERIA_NO_PERMITIDA = 'galeria_no_permitida', 'Foto de galería sin estar habilitada'

    class OrigenAnterior(models.TextChoices):
        LECTURA = 'lectura', 'Lectura anterior'
        INSTALACION = 'instalacion', 'Lectura inicial de la instalación'

    class OrigenFoto(models.TextChoices):
        CAMARA = 'camara', 'Cámara'
        GALERIA = 'galeria', 'Galería'

    comprobante = models.CharField('código de comprobante', max_length=12)
    id_operacion = models.UUIDField('identificador de operación del dispositivo')
    recorrido = models.ForeignKey('recorridos.Recorrido', on_delete=models.PROTECT, related_name='lecturas',
                                  verbose_name='recorrido')
    conexion = models.ForeignKey('padron.Conexion', on_delete=models.PROTECT, related_name='lecturas',
                                 verbose_name='conexión')
    instalacion = models.ForeignKey('padron.InstalacionMedidor', on_delete=models.PROTECT, related_name='lecturas',
                                    verbose_name='instalación del medidor')
    medidor = models.ForeignKey('padron.Medidor', on_delete=models.PROTECT, related_name='lecturas',
                                verbose_name='medidor')
    periodo = models.CharField('período', max_length=7, db_index=True)
    lectura_anterior = models.DecimalField('lectura anterior', max_digits=12, decimal_places=DECIMALES_LECTURA)
    fecha_lectura_anterior = models.DateField('fecha de la lectura anterior')
    origen_anterior = models.CharField('origen de la lectura anterior', max_length=12, choices=OrigenAnterior.choices)
    lectura_actual = models.DecimalField('lectura actual', max_digits=12, decimal_places=DECIMALES_LECTURA)
    consumo = models.DecimalField('consumo', max_digits=12, decimal_places=DECIMALES_LECTURA, null=True, blank=True,
                                  help_text='Vacío mientras requiere revisión. Lo calcula siempre el servidor.')
    capturada_en = models.DateTimeField('capturada el (teléfono)')
    sincronizada_en = models.DateTimeField('recibida en el servidor', auto_now_add=True)
    cobrador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='lecturas',
                                 verbose_name='cobrador')
    latitud = models.DecimalField('latitud', max_digits=9, decimal_places=6)
    longitud = models.DecimalField('longitud', max_digits=9, decimal_places=6)
    precision_metros = models.PositiveIntegerField('precisión del GPS (m)', null=True, blank=True)
    distancia_metros = models.PositiveIntegerField('distancia a la conexión (m)', null=True, blank=True,
                                                   help_text='Si la conexión tiene ubicación cargada.')
    foto_origen = models.CharField('origen de la foto', max_length=8, choices=OrigenFoto.choices,
                                   default=OrigenFoto.CAMARA)
    estado = models.CharField('estado', max_length=18, choices=Estado.choices, db_index=True)
    motivo_revision = models.CharField('motivo de revisión', max_length=20, choices=MotivoRevision.choices,
                                       blank=True)
    comentario = models.TextField('comentario del cobrador', blank=True)
    resuelta_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='+', verbose_name='resuelta por')
    resuelta_en = models.DateTimeField('resuelta el', null=True, blank=True)
    resolucion = models.TextField('motivo de la autorización, corrección o anulación', blank=True)

    class Meta:
        verbose_name = 'lectura'
        verbose_name_plural = 'lecturas'
        ordering = ['-capturada_en']
        constraints = [
            models.UniqueConstraint(fields=['institucion', 'comprobante'], name='lectura_comprobante_unico'),
            models.UniqueConstraint(fields=['institucion', 'id_operacion'], name='lectura_operacion_unica'),
            # Una sola lectura confirmada por instalación y período (prueba obligatoria 4).
            models.UniqueConstraint(fields=['instalacion', 'periodo'], condition=Q(estado='confirmada'),
                                    name='una_lectura_confirmada_por_periodo'),
            models.CheckConstraint(condition=Q(lectura_actual__gte=0), name='lectura_actual_no_negativa'),
            models.CheckConstraint(condition=Q(consumo__isnull=True) | Q(consumo__gte=0), name='consumo_no_negativo'),
            models.CheckConstraint(condition=~Q(estado='confirmada') | Q(consumo__isnull=False),
                                   name='confirmada_con_consumo'),
        ]
        indexes = [models.Index(fields=['institucion', 'periodo', 'estado'])]

    def __str__(self):
        return f'{self.comprobante} · {self.conexion.Code} {self.periodo}'


class FotoLectura(ModeloInstitucional):
    """Fotos de la lectura (archivos privados). La principal es obligatoria."""

    lectura = models.ForeignKey(Lectura, on_delete=models.PROTECT, related_name='fotos', verbose_name='lectura')
    archivo = models.CharField('archivo privado', max_length=255)
    principal = models.BooleanField('principal (medidor)', default=False)
    origen = models.CharField('origen', max_length=8, choices=Lectura.OrigenFoto.choices, default='camara')
    orden = models.PositiveSmallIntegerField('orden', default=0)

    class Meta:
        verbose_name = 'foto de lectura'
        verbose_name_plural = 'fotos de lecturas'
        ordering = ['-principal', 'orden', 'id']
        constraints = [
            models.UniqueConstraint(fields=['lectura'], condition=Q(principal=True), name='una_foto_principal'),
        ]
