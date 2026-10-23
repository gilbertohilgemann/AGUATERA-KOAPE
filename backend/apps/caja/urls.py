from django.urls import path
from rest_framework.routers import SimpleRouter

from . import vistas

enrutador = SimpleRouter()
enrutador.register('cajas', vistas.CajaVista, basename='caja')
enrutador.register('sesiones-caja', vistas.SesionCajaVista, basename='sesion_caja')
enrutador.register('gastos', vistas.GastoVista, basename='gasto')
enrutador.register('categorias-gasto', vistas.CategoriaGastoVista, basename='categoria_gasto')

urlpatterns = [path('caja/mi-sesion/', vistas.MiCajaVista.as_view(), name='mi_caja')] + enrutador.urls
