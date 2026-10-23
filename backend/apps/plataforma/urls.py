from django.urls import path

from . import vistas

urlpatterns = [
    path('institucion/', vistas.InstitucionVista.as_view(), name='institucion'),
]
