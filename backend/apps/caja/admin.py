"""Caja y gastos: solo lectura en el admin de la plataforma (se operan desde el panel de cada institución)."""
from django.contrib import admin

from .models import Caja, Gasto, SesionCaja


class _SoloLectura(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Caja)
class CajaAdmin(_SoloLectura):
    list_display = ('institucion', 'Code', 'nombre', 'activa')


@admin.register(SesionCaja)
class SesionCajaAdmin(_SoloLectura):
    list_display = ('institucion', 'referencia', 'caja', 'responsable', 'abierta_en', 'estado')
    list_filter = ('estado', 'institucion')


@admin.register(Gasto)
class GastoAdmin(_SoloLectura):
    list_display = ('institucion', 'referencia', 'fecha', 'motivo', 'importe', 'estado')
    list_filter = ('estado', 'institucion')
