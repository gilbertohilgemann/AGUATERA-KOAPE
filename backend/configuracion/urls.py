"""
Rutas principales.

- `/admin/`            → panel de la PLATAFORMA (superusuario): instituciones, migración, backup, manual.
- `/api/v1/salud/`     → verificación de estado (sin datos).
- `/api/v1/…`          → API de las instituciones. La institución sale SIEMPRE del token de la sesión.
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def salud(_request):
    """Responde sin tocar datos; sirve para monitoreo."""
    return JsonResponse({'estado': 'ok'})


admin.site.site_header = 'Koape Aguateras — Administración de la plataforma'
admin.site.site_title = 'Koape Aguateras'
admin.site.index_title = 'Instituciones y herramientas de la plataforma'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/salud/', salud, name='salud'),
    path('api/v1/', include('apps.identidad.urls')),
    path('api/v1/', include('apps.plataforma.urls')),
    path('api/v1/', include('apps.auditoria.urls')),
    path('api/v1/', include('apps.territorio.urls')),
    path('api/v1/', include('apps.padron.urls')),
    path('api/v1/', include('apps.facturacion.urls')),
    path('api/v1/', include('apps.recorridos.urls')),
    path('api/v1/', include('apps.lecturas.urls')),
    path('api/v1/', include('apps.tarifas.urls')),
    path('api/v1/', include('apps.cobranzas.urls')),
    path('api/v1/', include('apps.caja.urls')),
    path('api/v1/', include('apps.informes.urls')),
    path('api/v1/', include('apps.integraciones.urls')),
    path('api/v1/', include('apps.portal.urls')),
]
