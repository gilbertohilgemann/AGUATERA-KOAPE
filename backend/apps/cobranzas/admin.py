"""Pagos y recibos: solo lectura en el admin de la plataforma (se operan desde el panel de cada institución)."""
from django.contrib import admin

from .models import FormaPago, Pago, Recibo


class _SoloLectura(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FormaPago)
class FormaPagoAdmin(_SoloLectura):
    list_display = ('institucion', 'Code', 'nombre', 'tipo', 'activa')
    list_filter = ('tipo', 'activa', 'institucion')


@admin.register(Pago)
class PagoAdmin(_SoloLectura):
    list_display = ('institucion', 'referencia', 'fecha_hora', 'cliente', 'importe', 'forma_pago', 'origen', 'estado')
    list_filter = ('origen', 'estado', 'institucion')
    exclude = ('clave_idempotencia',)


@admin.register(Recibo)
class ReciboAdmin(_SoloLectura):
    list_display = ('institucion', 'numero', 'fecha_hora', 'cliente_nombre', 'importe', 'estado')
    list_filter = ('estado', 'institucion')
