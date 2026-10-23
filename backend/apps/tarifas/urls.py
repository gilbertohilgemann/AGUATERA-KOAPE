from django.urls import path
from rest_framework.routers import SimpleRouter

from . import vistas

enrutador = SimpleRouter()
enrutador.register('tarifas', vistas.TarifaVista, basename='tarifa')
enrutador.register('liquidaciones', vistas.LiquidacionVista, basename='liquidacion')

urlpatterns = [path('liquidaciones-resumen/', vistas.ResumenLiquidacionVista.as_view(), name='resumen_liquidaciones')] \
    + enrutador.urls
