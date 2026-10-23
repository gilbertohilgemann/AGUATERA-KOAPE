from django import forms
from django.contrib.auth.password_validation import validate_password

from .models import Institucion


class AltaInstitucionForm(forms.ModelForm):
    """Alta de una institución junto con su administrador inicial."""

    admin_usuario = forms.CharField(label='Usuario del administrador', initial='admin', max_length=150)
    admin_nombre = forms.CharField(label='Nombre del administrador', required=False, max_length=150)
    admin_correo = forms.EmailField(label='Correo del administrador', required=False)
    admin_contrasena = forms.CharField(
        label='Contraseña inicial', widget=forms.PasswordInput, strip=False,
        help_text='Se la pasa al cliente: al primer ingreso el sistema le pide cambiarla.',
    )

    class Meta:
        model = Institucion
        fields = ('codigo', 'nombre', 'ruc', 'direccion', 'telefono', 'correo', 'contacto', 'logo',
                  'zona_horaria', 'configuracion_regional')

    def clean_codigo(self):
        return self.cleaned_data['codigo'].strip().upper()

    def clean_admin_contrasena(self):
        valor = self.cleaned_data['admin_contrasena']
        validate_password(valor)
        return valor


class CambioEstadoForm(forms.Form):
    estado = forms.ChoiceField(label='Nuevo estado', choices=Institucion.Estado.choices)
    motivo = forms.CharField(label='Motivo', widget=forms.Textarea(attrs={'rows': 3}),
                             help_text='Obligatorio: queda en la auditoría.')
