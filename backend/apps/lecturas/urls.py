from rest_framework.routers import SimpleRouter

from . import vistas

enrutador = SimpleRouter()
enrutador.register('lecturas', vistas.LecturaVista, basename='lectura')
enrutador.register('cobrador/lecturas', vistas.LecturaCobradorVista, basename='mi_lectura')

urlpatterns = enrutador.urls
