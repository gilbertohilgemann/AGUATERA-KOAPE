from rest_framework.routers import SimpleRouter

from . import vistas

enrutador = SimpleRouter()
enrutador.register('zonas', vistas.ZonaVista, basename='zona')
enrutador.register('barrios', vistas.BarrioVista, basename='barrio')

urlpatterns = enrutador.urls
