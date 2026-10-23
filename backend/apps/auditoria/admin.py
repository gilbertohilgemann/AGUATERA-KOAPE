"""Auditoría en el panel de la plataforma: solo lectura (ni alta, ni edición, ni borrado)."""
from django.contrib import admin

from .models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ('ocurrido_en', 'institucion', 'usuario_nombre', 'accion', 'entidad', 'entidad_id', 'resultado', 'ip')
    list_filter = ('resultado', 'institucion', 'accion')
    search_fields = ('usuario_nombre', 'accion', 'entidad', 'entidad_id', 'motivo', 'id_solicitud')
    date_hierarchy = 'ocurrido_en'
    actions = None

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
