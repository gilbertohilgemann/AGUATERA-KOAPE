from django.urls import path
from rest_framework.routers import SimpleRouter

from . import vistas

enrutador = SimpleRouter()
enrutador.register('integraciones/credenciales', vistas.CredencialVista, basename='credencial_integracion')

urlpatterns = [path('integraciones/permisos/', vistas.PermisosAsignablesVista.as_view(), name='permisos_integracion')] \
    + enrutador.urls
