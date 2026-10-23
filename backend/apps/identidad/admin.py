"""
Usuarios en el panel de la plataforma.

- Usuarios de la PLATAFORMA (sin institución): se crean y administran acá.
- Usuarios de una INSTITUCIÓN: los administra cada institución desde su sistema. Acá solo se
  consultan y, si una institución perdió el acceso de su administrador, el superusuario puede
  restablecerle la contraseña (queda en la auditoría y se le pedirá cambiarla al ingresar).
"""
from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm, ReadOnlyPasswordHashField
from django.contrib.auth.password_validation import validate_password

from apps.auditoria.servicios import registrar

from .models import Permiso, Usuario
from .tokens import revocar_todos


class AltaUsuarioPlataformaForm(forms.ModelForm):
    contrasena1 = forms.CharField(label='Contraseña', widget=forms.PasswordInput, strip=False)
    contrasena2 = forms.CharField(label='Repetir contraseña', widget=forms.PasswordInput, strip=False)

    class Meta:
        model = Usuario
        fields = ('nombre_usuario', 'nombre', 'apellido', 'correo')

    def clean_nombre_usuario(self):
        valor = self.cleaned_data['nombre_usuario'].strip().lower()
        if Usuario.objects.filter(institucion__isnull=True, nombre_usuario=valor).exists():
            raise forms.ValidationError('Ya existe un usuario de plataforma con ese nombre.')
        return valor

    def clean(self):
        datos = super().clean()
        if datos.get('contrasena1') != datos.get('contrasena2'):
            raise forms.ValidationError('Las contraseñas no coinciden.')
        if datos.get('contrasena1'):
            validate_password(datos['contrasena1'])
        return datos

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.institucion = None
        usuario.is_staff = True
        usuario.set_password(self.cleaned_data['contrasena1'])
        if commit:
            usuario.save()
        return usuario


class EdicionUsuarioForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(
        label='Contraseña',
        help_text='Las contraseñas no se guardan en texto plano. Use el formulario «Restablecer contraseña».',
    )

    class Meta:
        model = Usuario
        fields = '__all__'


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    form = EdicionUsuarioForm
    add_form = AltaUsuarioPlataformaForm
    change_password_form = AdminPasswordChangeForm
    list_display = ('identificador', 'institucion', 'nombre', 'apellido', 'is_active', 'es_admin_institucion',
                    'is_superuser', 'last_login')
    list_filter = ('institucion', 'is_active', 'es_admin_institucion', 'is_superuser')
    search_fields = ('identificador', 'nombre', 'apellido', 'correo')
    ordering = ('institucion__codigo', 'nombre_usuario')
    filter_horizontal = ()
    readonly_fields = ('identificador', 'institucion', 'nombre_usuario', 'last_login', 'creado_en', 'actualizado_en',
                       'es_admin_institucion', 'intentos_fallidos', 'bloqueado_hasta', 'debe_cambiar_contrasena')
    fieldsets = (
        (None, {'fields': ('identificador', 'institucion', 'nombre_usuario', 'password')}),
        ('Datos personales', {'fields': ('nombre', 'apellido', 'correo')}),
        ('Estado y acceso', {'fields': ('is_active', 'is_staff', 'is_superuser', 'es_admin_institucion',
                                        'debe_cambiar_contrasena', 'intentos_fallidos', 'bloqueado_hasta')}),
        ('Fechas', {'fields': ('last_login', 'creado_en', 'actualizado_en')}),
    )
    add_fieldsets = (
        ('Usuario de la plataforma', {'fields': ('nombre_usuario', 'nombre', 'apellido', 'correo',
                                                 'contrasena1', 'contrasena2')}),
    )

    def get_readonly_fields(self, request, obj=None):
        campos = list(super().get_readonly_fields(request, obj))
        if obj is not None and obj.institucion_id is not None:
            # El acceso al panel de la plataforma nunca se da a un usuario de institución.
            campos += ['is_staff', 'is_superuser']
        return campos

    def has_delete_permission(self, request, obj=None):
        return False  # los usuarios se desactivan, no se borran

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        registrar('usuario_modificado' if change else 'usuario_plataforma_creado', request=request, usuario=request.user,
                  institucion=obj.institucion, entidad='usuario', entidad_id=obj.nombre_usuario,
                  campos=sorted(form.changed_data))

    def user_change_password(self, request, id, form_url=''):
        respuesta = super().user_change_password(request, id, form_url)
        if request.method == 'POST' and respuesta.status_code == 302:
            usuario = Usuario.objects.get(pk=id)
            if usuario.institucion_id is not None:
                usuario.debe_cambiar_contrasena = True
                usuario.intentos_fallidos = 0
                usuario.bloqueado_hasta = None
                usuario.save(update_fields=['debe_cambiar_contrasena', 'intentos_fallidos', 'bloqueado_hasta'])
                messages.info(request, 'El usuario deberá cambiar la contraseña al ingresar.')
            revocar_todos(usuario)
            registrar('contrasena_restablecida_por_plataforma', request=request, usuario=request.user,
                      institucion=usuario.institucion, entidad='usuario', entidad_id=usuario.nombre_usuario,
                      usuario_afectado=usuario.identificador)
        return respuesta


@admin.register(Permiso)
class PermisoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'descripcion', 'modulo', 'vigente')
    list_filter = ('modulo', 'vigente')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
