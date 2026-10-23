from django.urls import path

from . import vistas

urlpatterns = [
    path('informes/', vistas.CatalogoInformesVista.as_view(), name='informes'),
    path('informes/panel/', vistas.PanelVista.as_view(), name='panel'),
    path('informes/<slug:codigo>/', vistas.InformeVista.as_view(), name='informe'),
]
