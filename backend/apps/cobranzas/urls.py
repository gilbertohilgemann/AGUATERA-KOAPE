from django.urls import path
from rest_framework.routers import SimpleRouter

from . import vistas

enrutador = SimpleRouter()
enrutador.register('formas-pago', vistas.FormaPagoVista, basename='forma_pago')
enrutador.register('recibos', vistas.ReciboVista, basename='recibo')
enrutador.register('pagos', vistas.PagoVista, basename='pago')

urlpatterns = [path('cobranzas/estado-cuenta/', vistas.EstadoCuentaVista.as_view(), name='estado_cuenta')] \
    + enrutador.urls
