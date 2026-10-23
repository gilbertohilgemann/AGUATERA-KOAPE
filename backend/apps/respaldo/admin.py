"""Panel «Backup completo y seguridad» (patrón sin tabla)."""
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib import admin, messages
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import path

from apps.auditoria.servicios import registrar
from apps.plataforma.seguridad import revisar

from .models import Respaldo
from .servicios import generar_respaldo, limpiar_viejos, respaldos_guardados

PANEL = 'admin:respaldo_respaldo_changelist'


@admin.register(Respaldo)
class RespaldoAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        contexto = {
            **self.admin_site.each_context(request), 'opts': self.model._meta, 'title': 'Backup completo y seguridad',
            'hallazgos': revisar(), 'conservar': settings.KOAPE['RESPALDOS_A_CONSERVAR'],
            'recientes': [{'nombre': p.name, 'megas': round(p.stat().st_size / 1_048_576, 1),
                           'fecha': datetime.fromtimestamp(p.stat().st_mtime)} for p in respaldos_guardados()],
        }
        return render(request, 'admin/respaldo/panel.html', contexto)

    def get_urls(self):
        return [
            path('descargar/', self.admin_site.admin_view(self.descargar), name='respaldo_descargar'),
            path('archivo/<str:nombre>/', self.admin_site.admin_view(self.archivo), name='respaldo_archivo'),
        ] + super().get_urls()

    def descargar(self, request):
        if request.method != 'POST' or not request.user.is_superuser:
            return redirect(PANEL)
        try:
            archivo = generar_respaldo()
        except Exception as error:
            messages.error(request, f'No se pudo generar el backup: {error}')
            return redirect(PANEL)
        limpiar_viejos(archivo.parent, settings.KOAPE['RESPALDOS_A_CONSERVAR'])  # no llenar el disco
        registrar('backup_generado', request=request, usuario=request.user, entidad='respaldo', entidad_id=archivo.name,
                  tamanio=archivo.stat().st_size)
        return FileResponse(open(archivo, 'rb'), as_attachment=True, filename=archivo.name)

    def archivo(self, request, nombre):
        """Descarga uno de los backups guardados (solo superusuario; solo archivos de esa carpeta)."""
        if not request.user.is_superuser:
            return redirect(PANEL)
        carpeta = Path(settings.DIR_RESPALDOS).resolve()
        ruta = (carpeta / nombre).resolve()
        if ruta.parent != carpeta or ruta.suffix != '.zip' or not ruta.is_file():
            raise Http404('No existe ese respaldo.')
        registrar('backup_descargado', request=request, usuario=request.user, entidad='respaldo', entidad_id=ruta.name)
        return FileResponse(open(ruta, 'rb'), as_attachment=True, filename=ruta.name)
