"""
Serializadores de identidad.

Los campos que referencian otros registros (roles, permisos) se arman por solicitud con la consulta
YA FILTRADA por la institución de la sesión: un id de otra institución responde «no existe».
"""
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError as ErrorValidacionDjango
from rest_framework import serializers

from comun.codigos import CodeSerializerField

from .models import Permiso, Rol, Usuario
from .permisos import permisos_efectivos


def permisos_de_roles(roles) -> set[str]:
    return set(Permiso.objects.filter(vigente=True, roles__in=list(roles)).values_list('codigo', flat=True))


def puede_gestionar(actor, usuario) -> bool:
    """
    Regla contra la escalada de privilegios: quien no es administrador institucional solo gestiona
    (edita, desactiva, restablece la contraseña) a usuarios con permisos que él mismo tiene, y nunca
    a un administrador.
    """
    if actor.es_admin_institucion:
        return True
    if usuario.es_admin_institucion:
        return False
    return permisos_efectivos(usuario) <= permisos_efectivos(actor)


def _validar_contrasena(valor, usuario=None):
    try:
        validate_password(valor, user=usuario)
    except ErrorValidacionDjango as error:
        raise serializers.ValidationError(list(error.messages))
    return valor


class IngresoSerializer(serializers.Serializer):
    codigo_institucion = serializers.CharField(max_length=20)
    usuario = serializers.CharField(max_length=150)
    contrasena = serializers.CharField(max_length=128, trim_whitespace=False)
    # Campo trampa (honeypot): invisible para personas; si llega con algo, es un bot.
    sitio_web = serializers.CharField(required=False, allow_blank=True)


class SolicitarRecuperacionSerializer(serializers.Serializer):
    codigo_institucion = serializers.CharField(max_length=20)
    usuario = serializers.CharField(max_length=150)


class ConfirmarRecuperacionSerializer(SolicitarRecuperacionSerializer):
    codigo = serializers.CharField(max_length=12)
    contrasena_nueva = serializers.CharField(max_length=128, trim_whitespace=False)


class CambioContrasenaSerializer(serializers.Serializer):
    contrasena_actual = serializers.CharField(trim_whitespace=False)
    contrasena_nueva = serializers.CharField(trim_whitespace=False)

    def validate(self, datos):
        usuario = self.context['request'].user
        if not usuario.check_password(datos['contrasena_actual']):
            raise serializers.ValidationError({'contrasena_actual': 'La contraseña actual no es correcta.'})
        if datos['contrasena_actual'] == datos['contrasena_nueva']:
            raise serializers.ValidationError({'contrasena_nueva': 'La contraseña nueva debe ser distinta de la actual.'})
        _validar_contrasena(datos['contrasena_nueva'], usuario)
        return datos


class RestablecerContrasenaSerializer(serializers.Serializer):
    contrasena_nueva = serializers.CharField(trim_whitespace=False)

    def validate_contrasena_nueva(self, valor):
        return _validar_contrasena(valor)


class PermisoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permiso
        fields = ['id', 'codigo', 'descripcion', 'modulo']


class RolSerializer(serializers.ModelSerializer):
    permisos = serializers.SlugRelatedField(many=True, slug_field='codigo', queryset=Permiso.objects.none(),
                                            required=False)
    cantidad_usuarios = serializers.SerializerMethodField()
    Code = CodeSerializerField()

    class Meta:
        model = Rol
        fields = ['id', 'Code', 'nombre', 'descripcion', 'permisos', 'activo', 'cantidad_usuarios']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Todos (no solo vigentes): un rol que conserva un permiso retirado se puede volver a guardar.
        self.fields['permisos'].child_relation.queryset = Permiso.objects.all()

    def validate_permisos(self, permisos):
        actuales = set(self.instance.permisos.values_list('codigo', flat=True)) if self.instance else set()
        nuevos = {p.codigo for p in permisos} - actuales
        retirados = sorted(p.codigo for p in permisos if p.codigo in nuevos and not p.vigente)
        if retirados:
            raise serializers.ValidationError(f'Permisos que ya no existen: {", ".join(retirados)}.')
        actor = self.context['request'].user
        if not actor.es_admin_institucion:
            ajenos = sorted(nuevos - permisos_efectivos(actor))
            if ajenos:
                raise serializers.ValidationError(
                    f'Solo puede otorgar permisos que usted tiene. No tiene: {", ".join(ajenos)}.')
        return permisos

    def get_cantidad_usuarios(self, rol) -> int:
        return rol.usuarios.filter(is_active=True).count()

    def validate_Code(self, valor):
        consulta = Rol.objects.de(self.context['institucion']).filter(Code=valor)
        if self.instance is not None:
            consulta = consulta.exclude(pk=self.instance.pk)
        if consulta.exists():
            raise serializers.ValidationError('Ya existe un rol con ese código.')
        return valor

    def validate_nombre(self, valor):
        institucion = self.context['institucion']
        consulta = Rol.objects.de(institucion).filter(nombre__iexact=valor.strip())
        if self.instance is not None:
            consulta = consulta.exclude(pk=self.instance.pk)
        if consulta.exists():
            raise serializers.ValidationError('Ya existe un rol con ese nombre.')
        return valor.strip()


class UsuarioSerializer(serializers.ModelSerializer):
    usuario = serializers.CharField(source='nombre_usuario', max_length=150, validators=[UnicodeUsernameValidator()])
    activo = serializers.BooleanField(source='is_active', required=False)
    ultimo_ingreso = serializers.DateTimeField(source='last_login', read_only=True)
    bloqueado = serializers.SerializerMethodField()
    contrasena = serializers.CharField(write_only=True, required=False, trim_whitespace=False)
    roles = serializers.PrimaryKeyRelatedField(many=True, queryset=Rol.objects.none(), required=False)

    class Meta:
        model = Usuario
        fields = ['id', 'usuario', 'nombre', 'apellido', 'correo', 'activo', 'es_admin_institucion', 'roles',
                  'ultimo_ingreso', 'debe_cambiar_contrasena', 'bloqueado', 'contrasena']
        read_only_fields = ['debe_cambiar_contrasena']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        institucion = self.context.get('institucion')
        self.fields['roles'].child_relation.queryset = Rol.objects.de(institucion).filter(activo=True)

    def get_bloqueado(self, usuario) -> bool:
        from django.utils import timezone
        return bool(usuario.bloqueado_hasta and usuario.bloqueado_hasta > timezone.now())

    def validate_usuario(self, valor):
        valor = valor.strip().lower()
        # El nombre de usuario es la clave visible del usuario (su «Code»): no se cambia después del alta.
        if self.instance is not None and valor != self.instance.nombre_usuario:
            raise serializers.ValidationError('El nombre de usuario no se cambia después del alta.')
        consulta = Usuario.objects.de(self.context['institucion']).filter(nombre_usuario=valor)
        if self.instance is not None:
            consulta = consulta.exclude(pk=self.instance.pk)
        if consulta.exists():
            raise serializers.ValidationError('Ya existe un usuario con ese nombre en la institución.')
        return valor

    def validate(self, datos):
        actual = self.context['request'].user
        if self.instance is None and not datos.get('contrasena'):
            raise serializers.ValidationError({'contrasena': 'La contraseña es obligatoria al crear un usuario.'})
        if datos.get('contrasena'):
            _validar_contrasena(datos['contrasena'])
        # Solo un administrador institucional da (o quita) esa condición, o modifica a otro administrador:
        # quien solo tiene «usuarios.administrar» no puede convertirse en administrador.
        toca_admin = 'es_admin_institucion' in datos and (
            self.instance is None and datos['es_admin_institucion']
            or self.instance is not None and datos['es_admin_institucion'] != self.instance.es_admin_institucion
        )
        if (toca_admin or (self.instance is not None and self.instance.es_admin_institucion)) \
                and not actual.es_admin_institucion:
            raise serializers.ValidationError(
                {'es_admin_institucion': 'Solo un administrador institucional puede gestionar administradores.'})
        if not actual.es_admin_institucion:
            if self.instance is not None and not puede_gestionar(actual, self.instance):
                raise serializers.ValidationError(
                    'No puede modificar a un usuario con permisos que usted no tiene.')
            if 'roles' in datos:
                anteriores = set(self.instance.roles.all()) if self.instance is not None else set()
                if self.instance is not None and self.instance.pk == actual.pk and set(datos['roles']) != anteriores:
                    raise serializers.ValidationError({'roles': 'No puede cambiar sus propios roles.'})
                ajenos = sorted(permisos_de_roles(set(datos['roles']) - anteriores) - permisos_efectivos(actual))
                if ajenos:
                    raise serializers.ValidationError(
                        {'roles': f'Solo puede asignar roles con permisos que usted tiene. No tiene: {", ".join(ajenos)}.'})
        if self.instance is not None and self.instance.pk == actual.pk:
            if datos.get('is_active') is False:
                raise serializers.ValidationError({'activo': 'No puede desactivar su propio usuario.'})
            if datos.get('es_admin_institucion') is False:
                raise serializers.ValidationError(
                    {'es_admin_institucion': 'No puede quitarse a sí mismo la condición de administrador.'})
        return datos

    def create(self, datos):
        contrasena = datos.pop('contrasena')
        roles = datos.pop('roles', [])
        usuario = Usuario(institucion=self.context['institucion'], debe_cambiar_contrasena=True, **datos)
        usuario.set_password(contrasena)
        usuario.save()
        usuario.roles.set(roles)
        return usuario

    def update(self, usuario, datos):
        datos.pop('contrasena', None)  # la contraseña se cambia solo con «restablecer contraseña»
        roles = datos.pop('roles', None)
        for campo, valor in datos.items():
            setattr(usuario, campo, valor)
        usuario.save()
        if roles is not None:
            usuario.roles.set(roles)
        return usuario
