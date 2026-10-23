"""Numeración: solo lectura en el admin (la configura cada institución). Proveedor electrónico: lo carga la plataforma."""
import json

from django import forms
from django.contrib import admin

from comun.cifrado import cifrar

from .models import ProveedorFacturacion, PuntoExpedicion, RangoNumeracion


class _SoloLectura(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PuntoExpedicion)
class PuntoExpedicionAdmin(_SoloLectura):
    list_display = ('institucion', 'Code', 'establecimiento', 'punto', 'nombre', 'activo')
    list_filter = ('activo', 'institucion')


@admin.register(RangoNumeracion)
class RangoNumeracionAdmin(_SoloLectura):
    list_display = ('institucion', 'Code', 'punto', 'tipo_documento', 'timbrado', 'desde', 'hasta', 'activo')
    list_filter = ('tipo_documento', 'activo', 'institucion')
    exclude = ('ultimo_usado',)


class ProveedorForm(forms.ModelForm):
    """Las credenciales se escriben (JSON) y se guardan cifradas; nunca se vuelven a mostrar."""

    credenciales_nuevas = forms.CharField(
        label='credenciales (JSON)', required=False, widget=forms.PasswordInput(render_value=False),
        help_text='Déjelo vacío para conservar las actuales. Se guardan cifradas y no se vuelven a mostrar.')

    class Meta:
        model = ProveedorFacturacion
        fields = ('institucion', 'nombre', 'adaptador', 'ambiente', 'activo')

    def clean_credenciales_nuevas(self):
        valor = self.cleaned_data.get('credenciales_nuevas', '').strip()
        if valor:
            try:
                if not isinstance(json.loads(valor), dict):
                    raise ValueError
            except ValueError:
                raise forms.ValidationError('Debe ser un objeto JSON, por ejemplo {"usuario": "…", "clave": "…"}.')
        return valor

    def save(self, commit=True):
        proveedor = super().save(commit=False)
        if self.cleaned_data.get('credenciales_nuevas'):
            proveedor.credenciales = cifrar(self.cleaned_data['credenciales_nuevas'])
        if commit:
            proveedor.save()
        return proveedor


@admin.register(ProveedorFacturacion)
class ProveedorFacturacionAdmin(admin.ModelAdmin):
    form = ProveedorForm
    list_display = ('institucion', 'nombre', 'adaptador', 'ambiente', 'activo', 'con_credenciales')
    list_filter = ('ambiente', 'activo')

    @admin.display(boolean=True, description='credenciales')
    def con_credenciales(self, obj):
        return bool(obj.credenciales)

    def has_delete_permission(self, request, obj=None):
        return False
