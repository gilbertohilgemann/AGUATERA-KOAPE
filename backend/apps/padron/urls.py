from django.urls import path
from rest_framework.routers import SimpleRouter

from . import vistas

enrutador = SimpleRouter()
enrutador.register('clientes', vistas.ClienteVista, basename='cliente')
enrutador.register('conexiones', vistas.ConexionVista, basename='conexion')
enrutador.register('medidores', vistas.MedidorVista, basename='medidor')

urlpatterns = [
    path('mapa/', vistas.MapaVista.as_view(), name='mapa'),
    path('padron/resumen/', vistas.ResumenPadronVista.as_view(), name='resumen_padron'),
] + enrutador.urls
