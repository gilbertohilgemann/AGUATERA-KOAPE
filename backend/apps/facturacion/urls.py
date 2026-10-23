from django.urls import path
from rest_framework.routers import SimpleRouter

from . import vistas

enrutador = SimpleRouter()
enrutador.register('puntos-expedicion', vistas.PuntoExpedicionVista, basename='punto_expedicion')
enrutador.register('rangos-numeracion', vistas.RangoNumeracionVista, basename='rango_numeracion')
enrutador.register('facturas', vistas.FacturaVista, basename='factura')

urlpatterns = [path('facturacion/pendientes/', vistas.PendientesFacturarVista.as_view(), name='pendientes_facturar')] \
    + enrutador.urls
