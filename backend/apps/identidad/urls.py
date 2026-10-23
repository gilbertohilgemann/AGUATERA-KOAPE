from django.urls import path
from rest_framework.routers import SimpleRouter

from . import vistas

enrutador = SimpleRouter()
enrutador.register('usuarios', vistas.UsuarioVista, basename='usuario')
enrutador.register('roles', vistas.RolVista, basename='rol')
enrutador.register('permisos', vistas.PermisoVista, basename='permiso')

urlpatterns = [
    path('auth/ingresar/', vistas.IngresarVista.as_view(), name='ingresar'),
    path('auth/salir/', vistas.SalirVista.as_view(), name='salir'),
    path('auth/recuperar/', vistas.SolicitarRecuperacionVista.as_view(), name='recuperar'),
    path('auth/recuperar/confirmar/', vistas.ConfirmarRecuperacionVista.as_view(), name='recuperar_confirmar'),
    path('auth/yo/', vistas.YoVista.as_view(), name='yo'),
    path('auth/cambiar-contrasena/', vistas.CambiarContrasenaVista.as_view(), name='cambiar_contrasena'),
] + enrutador.urls
