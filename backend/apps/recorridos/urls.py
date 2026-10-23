from rest_framework.routers import SimpleRouter

from . import vistas

enrutador = SimpleRouter()
enrutador.register('recorridos', vistas.RecorridoVista, basename='recorrido')
enrutador.register('cobrador/recorridos', vistas.MisRecorridosVista, basename='mi_recorrido')

urlpatterns = enrutador.urls
