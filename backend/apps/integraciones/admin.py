from django.contrib import admin

from .models import CredencialIntegracion


@admin.register(CredencialIntegracion)
class CredencialIntegracionAdmin(admin.ModelAdmin):
    """Solo lectura: las crea y revoca el administrador de cada institución desde su panel."""
    list_display = ('institucion', 'nombre', 'prefijo', 'activa', 'ultimo_uso_en')
    list_filter = ('activa', 'institucion')
    exclude = ('clave_hash',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
