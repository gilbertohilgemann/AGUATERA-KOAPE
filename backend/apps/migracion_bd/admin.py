"""Panel «Migración de base de datos» (patrón sin tabla)."""
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path

from apps.auditoria.servicios import registrar

from . import db_migracion
from .formularios import PostgresFormulario
from .models import MigracionBaseDatos

PANEL = 'admin:migracion_bd_migracionbasedatos_changelist'


@admin.register(MigracionBaseDatos)
class MigracionBaseDatosAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        contexto = {
            **self.admin_site.each_context(request), 'opts': self.model._meta, 'title': 'Migración de base de datos',
            'estado': db_migracion.estado_actual(), 'formulario': PostgresFormulario(),
        }
        return render(request, 'admin/migracion_bd/panel.html', contexto)

    def get_urls(self):
        return [path('ejecutar/', self.admin_site.admin_view(self.ejecutar), name='migracion_bd_ejecutar')] + super().get_urls()

    def ejecutar(self, request):
        if request.method != 'POST' or not request.user.is_superuser:
            return redirect(PANEL)
        accion = request.POST.get('accion')
        try:
            if accion in {'probar', 'a_postgres'}:
                formulario = PostgresFormulario(request.POST)
                if not formulario.is_valid():
                    messages.error(request, 'Complete los datos de conexión a PostgreSQL.')
                    return redirect(PANEL)
                datos = db_migracion.DatosPostgres(**formulario.cleaned_data)
                if accion == 'probar':
                    db_migracion.probar_conexion(datos)
                    messages.success(request, 'Conexión a PostgreSQL correcta.')
                    return redirect(PANEL)
                resumen = db_migracion.migrar_a_postgres(datos)
            elif accion == 'a_sqlite':
                resumen = db_migracion.volver_a_sqlite()
            elif accion == 'traer':
                resumen = db_migracion.traer_datos_a_sqlite()
            else:
                return redirect(PANEL)
        except Exception as error:
            messages.error(request, f'La operación no se completó: {error}')
            registrar('migracion_bd_fallida', request=request, usuario=request.user, entidad='base_datos',
                      resultado='fallo', accion_panel=accion, error=str(error)[:500])
            return redirect(PANEL)
        registrar('migracion_bd', request=request, usuario=request.user, entidad='base_datos', accion_panel=accion,
                  resumen=resumen)
        for linea in resumen:
            messages.success(request, linea)
        return redirect(PANEL)
