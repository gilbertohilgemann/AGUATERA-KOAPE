from rest_framework.routers import SimpleRouter

from . import vistas

enrutador = SimpleRouter()
enrutador.register('auditoria', vistas.RegistroAuditoriaVista, basename='auditoria')

urlpatterns = enrutador.urls
