from django.urls import path

from . import vistas as v

urlpatterns = [
    path('portal/solicitar-pin/', v.SolicitarPinVista.as_view(), name='portal_pin'),
    path('portal/ingresar/', v.IngresarVista.as_view(), name='portal_ingresar'),
    path('portal/yo/', v.YoVista.as_view(), name='portal_yo'),
    path('portal/cambiar-clave/', v.CambiarClaveVista.as_view(), name='portal_clave'),
    path('portal/salir/', v.SalirVista.as_view(), name='portal_salir'),
    path('portal/resumen/', v.ResumenVista.as_view(), name='portal_resumen'),
    path('portal/<slug:codigo>/conexiones/', v.ConexionesVista.as_view(), name='portal_conexiones'),
    path('portal/<slug:codigo>/deuda/', v.DeudaVista.as_view(), name='portal_deuda'),
    path('portal/<slug:codigo>/facturas/', v.FacturasVista.as_view(), name='portal_facturas'),
    path('portal/<slug:codigo>/facturas/<str:referencia>/pdf/', v.FacturaPdfVista.as_view(), name='portal_factura_pdf'),
    path('portal/<slug:codigo>/pagos/', v.PagosVista.as_view(), name='portal_pagos'),
    path('portal/<slug:codigo>/recibos/<int:numero>/pdf/', v.ReciboPdfVista.as_view(), name='portal_recibo_pdf'),
    path('portal/<slug:codigo>/lecturas/', v.LecturasVista.as_view(), name='portal_lecturas'),
    path('portal/<slug:codigo>/lecturas/<str:comprobante>/foto/', v.FotoLecturaVista.as_view(), name='portal_foto'),
]
