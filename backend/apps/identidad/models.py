"""
Usuarios, roles, permisos y sesiones.

Una sola tabla de usuarios para toda la plataforma (base central, D2):

- `institucion` vacía  → usuario de la PLATAFORMA (entra solo al panel /admin/).
- `institucion` cargada → usuario de esa institución (entra al sistema con el código institucional).

El mismo nombre de usuario puede existir en dos instituciones («admin» en cada junta). Por eso el
campo con el que Django identifica al usuario (`identificador`) se arma solo:
`nombre_usuario` para la plataforma y `CODIGO/nombre_usuario` para una institución.
"""
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import models
from django.db.models import Q

from comun.codigos import campo_code
from comun.modelos import ConsultaInstitucional, ModeloInstitucional


def armar_identificador(nombre_usuario: str, institucion=None) -> str:
    nombre = (nombre_usuario or '').strip().lower()
    return f'{institucion.codigo}/{nombre}' if institucion is not None else nombre


class GestorUsuarios(BaseUserManager.from_queryset(ConsultaInstitucional)):
    use_in_migrations = True

    def _crear(self, nombre_usuario, password, institucion=None, **extra):
        if not nombre_usuario:
            raise ValueError('El nombre de usuario es obligatorio.')
        usuario = self.model(nombre_usuario=nombre_usuario, institucion=institucion, **extra)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, nombre_usuario=None, password=None, institucion=None, identificador=None, **extra):
        extra.setdefault('is_staff', False)
        extra.setdefault('is_superuser', False)
        return self._crear(nombre_usuario or identificador, password, institucion, **extra)

    def create_superuser(self, identificador=None, password=None, nombre_usuario=None, **extra):
        """Superusuario de la PLATAFORMA (sin institución). Lo usa `createsuperuser`."""
        extra['is_staff'] = True
        extra['is_superuser'] = True
        return self._crear(nombre_usuario or identificador, password, None, **extra)

    def get_by_natural_key(self, identificador):
        return self.get(identificador=identificador)


class Usuario(AbstractBaseUser, PermissionsMixin):
    institucion = models.ForeignKey(
        'plataforma.Institucion', null=True, blank=True, on_delete=models.PROTECT, related_name='usuarios',
        verbose_name='institución', help_text='Vacío = usuario de la plataforma.',
    )
    nombre_usuario = models.CharField('nombre de usuario', max_length=150, validators=[UnicodeUsernameValidator()])
    identificador = models.CharField(
        'identificador', max_length=180, unique=True, editable=False,
        help_text='Se arma solo: usuario (plataforma) o CODIGO/usuario (institución).',
    )
    nombre = models.CharField('nombre', max_length=150, blank=True)
    apellido = models.CharField('apellido', max_length=150, blank=True)
    correo = models.EmailField('correo electrónico', blank=True)
    is_active = models.BooleanField('activo', default=True)
    is_staff = models.BooleanField('acceso al panel de la plataforma', default=False)
    es_admin_institucion = models.BooleanField(
        'administrador institucional', default=False,
        help_text='Tiene todos los permisos de su institución.',
    )
    roles = models.ManyToManyField('identidad.Rol', blank=True, related_name='usuarios', verbose_name='roles')
    intentos_fallidos = models.PositiveSmallIntegerField('intentos fallidos', default=0)
    bloqueado_hasta = models.DateTimeField('bloqueado hasta', null=True, blank=True)
    debe_cambiar_contrasena = models.BooleanField('debe cambiar la contraseña', default=False)
    # Recuperación por correo (D51): solo el hash del código, con vencimiento, espera entre envíos e intentos.
    recuperacion_codigo = models.CharField('código de recuperación (hash)', max_length=128, blank=True, editable=False)
    recuperacion_vence_en = models.DateTimeField('código vence', null=True, blank=True, editable=False)
    recuperacion_enviada_en = models.DateTimeField('código enviado', null=True, blank=True, editable=False)
    recuperacion_intentos = models.PositiveSmallIntegerField('intentos con el código', default=0, editable=False)
    creado_en = models.DateTimeField('creado el', auto_now_add=True)
    actualizado_en = models.DateTimeField('actualizado el', auto_now=True)

    objects = GestorUsuarios()

    USERNAME_FIELD = 'identificador'
    EMAIL_FIELD = 'correo'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'
        ordering = ['institucion__codigo', 'nombre_usuario']
        constraints = [
            models.UniqueConstraint(fields=['institucion', 'nombre_usuario'], name='usuario_unico_por_institucion'),
            models.UniqueConstraint(fields=['nombre_usuario'], condition=Q(institucion__isnull=True),
                                    name='usuario_plataforma_unico'),
            # Un usuario de institución nunca entra al panel de la plataforma, y uno de plataforma
            # no puede ser administrador de una institución.
            models.CheckConstraint(
                condition=Q(institucion__isnull=True) | (Q(is_staff=False) & Q(is_superuser=False)),
                name='usuario_institucional_sin_panel_plataforma',
            ),
            models.CheckConstraint(
                condition=Q(institucion__isnull=False) | Q(es_admin_institucion=False),
                name='admin_institucional_con_institucion',
            ),
        ]

    def __str__(self):
        return self.identificador

    def save(self, *args, **kwargs):
        self.nombre_usuario = (self.nombre_usuario or '').strip().lower()
        self.identificador = armar_identificador(self.nombre_usuario, self.institucion)
        super().save(*args, **kwargs)

    @property
    def username(self) -> str:
        """Compatibilidad con código y plantillas que esperan `username`."""
        return self.nombre_usuario

    def get_full_name(self) -> str:
        return f'{self.nombre} {self.apellido}'.strip() or self.nombre_usuario

    def get_short_name(self) -> str:
        return self.nombre or self.nombre_usuario


class Permiso(models.Model):
    """Catálogo de permisos del sistema (común a todas las instituciones, ver `catalogo_permisos.py`)."""

    codigo = models.CharField('código', max_length=80, unique=True)
    descripcion = models.CharField('descripción', max_length=200)
    modulo = models.CharField('módulo', max_length=60)
    vigente = models.BooleanField('vigente', default=True)

    class Meta:
        verbose_name = 'permiso'
        verbose_name_plural = 'permisos'
        ordering = ['modulo', 'codigo']

    def __str__(self):
        return self.codigo


class Rol(ModeloInstitucional):
    """
    Rol de UNA institución: combinación de permisos granulares. Cada institución arma los suyos
    («Cajero», «Supervisor»…) sin tocar código. No se borran: se desactivan.
    """

    Code = campo_code('código del rol')
    nombre = models.CharField('nombre', max_length=80)
    descripcion = models.CharField('descripción', max_length=255, blank=True)
    permisos = models.ManyToManyField(Permiso, blank=True, related_name='roles', verbose_name='permisos')
    activo = models.BooleanField('activo', default=True)

    class Meta:
        verbose_name = 'rol'
        verbose_name_plural = 'roles'
        ordering = ['nombre']
        constraints = [
            models.UniqueConstraint(fields=['institucion', 'nombre'], name='rol_unico_por_institucion'),
            models.UniqueConstraint(fields=['institucion', 'Code'], name='rol_code_unico'),
        ]

    def __str__(self):
        return self.nombre


class TokenSesion(models.Model):
    """
    Sesión de la API. Solo se guarda el hash SHA-256 del token: quien copie la base no puede
    reutilizar sesiones. La institución de la sesión sale de acá y de ningún otro lado.
    """

    clave_hash = models.CharField('hash del token', max_length=64, unique=True)
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name='tokens', verbose_name='usuario')
    institucion = models.ForeignKey('plataforma.Institucion', on_delete=models.PROTECT, related_name='+',
                                    verbose_name='institución')
    creado_en = models.DateTimeField('creado el', auto_now_add=True)
    expira_en = models.DateTimeField('vence el')
    ultimo_uso = models.DateTimeField('último uso', null=True, blank=True)
    revocado_en = models.DateTimeField('revocado el', null=True, blank=True)
    ip = models.GenericIPAddressField('IP', null=True, blank=True)
    agente = models.CharField('navegador', max_length=255, blank=True)

    class Meta:
        verbose_name = 'sesión'
        verbose_name_plural = 'sesiones'
        indexes = [models.Index(fields=['usuario', 'revocado_en'])]

    def __str__(self):
        return f'Sesión de {self.usuario} ({self.creado_en:%d/%m/%Y %H:%M})'
