"""Datos de la institución de la sesión (ver y editar los datos de contacto)."""
from django.db import transaction
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditoria.servicios import registrar
from apps.identidad.permisos import RequierePermiso
from comun.vistas import institucion_de

from .models import Institucion
from .servicios import foto_institucion


class InstitucionSerializer(serializers.ModelSerializer):
    estado_nombre = serializers.CharField(source='get_estado_display', read_only=True)
    modalidad_facturacion_nombre = serializers.CharField(source='get_modalidad_facturacion_display', read_only=True)

    class Meta:
        model = Institucion
        fields = ['codigo', 'nombre', 'ruc', 'direccion', 'telefono', 'correo', 'contacto', 'logo', 'estado',
                  'estado_nombre', 'zona_horaria', 'configuracion_regional', 'modalidad_facturacion',
                  'modalidad_facturacion_nombre', 'lecturas_permite_galeria', 'dias_vencimiento_credito',
                  'aplicacion_pagos', 'portal_abonados', 'creado_en']
        # Código, estado y modalidad de facturación los define la plataforma: la modalidad depende de
        # las habilitaciones fiscales y no se puede cambiar desde la institución.
        read_only_fields = ['codigo', 'logo', 'estado', 'modalidad_facturacion', 'creado_en']

    def validate_dias_vencimiento_credito(self, valor):
        if valor > 365:
            raise serializers.ValidationError('Como máximo 365 días.')
        return valor

    def validate_zona_horaria(self, valor):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(valor)
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError('Zona horaria desconocida (ej. America/Asuncion).')
        return valor


class InstitucionVista(APIView):
    permission_classes = [IsAuthenticated, RequierePermiso]
    permiso_requerido = 'institucion.editar'
    permisos_lectura = ('institucion.ver',)

    def get(self, request):
        return Response(InstitucionSerializer(institucion_de(request)).data)

    def patch(self, request):
        institucion = institucion_de(request)
        antes = foto_institucion(institucion)
        serializador = InstitucionSerializer(institucion, data=request.data, partial=True)
        serializador.is_valid(raise_exception=True)
        with transaction.atomic():
            serializador.save()
            registrar('institucion_modificada', request=request, entidad='institucion', entidad_id=institucion.codigo,
                      antes=antes, despues=foto_institucion(institucion))
        return Response(serializador.data)
