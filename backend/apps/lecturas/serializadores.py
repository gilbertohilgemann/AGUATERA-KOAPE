"""Lecturas en la API: se identifican por su código de comprobante (L-XXXXXXXX), nunca por el id interno."""
from rest_framework import serializers

from .models import Lectura


class LecturaSerializer(serializers.ModelSerializer):
    conexion = serializers.CharField(source='conexion.Code')
    titular = serializers.CharField(source='conexion.cliente.nombre')
    direccion = serializers.CharField(source='conexion.direccion')
    medidor = serializers.CharField(source='medidor.Code')
    medidor_numero = serializers.CharField(source='medidor.numero', read_only=True)
    recorrido = serializers.CharField(source='recorrido.Code')
    cobrador = serializers.CharField(source='cobrador.nombre_usuario')
    cobrador_nombre = serializers.SerializerMethodField()
    estado_nombre = serializers.CharField(source='get_estado_display')
    motivo_revision_nombre = serializers.CharField(source='get_motivo_revision_display')
    resuelta_por = serializers.CharField(source='resuelta_por.nombre_usuario', default=None)
    fotos = serializers.SerializerMethodField()

    class Meta:
        model = Lectura
        fields = ['comprobante', 'id_operacion', 'periodo', 'recorrido', 'conexion', 'titular', 'direccion', 'medidor',
                  'medidor_numero',
                  'lectura_anterior', 'fecha_lectura_anterior', 'origen_anterior', 'lectura_actual', 'consumo',
                  'capturada_en', 'sincronizada_en', 'cobrador', 'cobrador_nombre', 'latitud', 'longitud',
                  'precision_metros', 'distancia_metros', 'foto_origen', 'estado', 'estado_nombre', 'motivo_revision',
                  'motivo_revision_nombre', 'comentario', 'resuelta_por', 'resuelta_en', 'resolucion', 'fotos']
        read_only_fields = fields

    def get_cobrador_nombre(self, l):
        return l.cobrador.get_full_name() or l.cobrador.nombre_usuario

    def get_fotos(self, l):
        # Posición en la lista (0 = principal): la foto se pide por esa posición, nunca por un id interno.
        return [{'n': n, 'principal': f.principal, 'origen': f.origen} for n, f in enumerate(l.fotos.all())]


class RegistroLecturaSerializer(serializers.Serializer):
    id_operacion = serializers.UUIDField()
    recorrido = serializers.CharField(max_length=40)
    medidor = serializers.CharField(max_length=40)
    lectura_actual = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0)
    capturada_en = serializers.DateTimeField()
    latitud = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitud = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    precision_metros = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    comentario = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    foto_origen = serializers.ChoiceField(choices=Lectura.OrigenFoto.choices, required=False)

    def to_internal_value(self, datos):
        # Precisión del GPS con decimales (algunos teléfonos la informan así): se redondea.
        if hasattr(datos, 'copy'):
            datos = datos.copy()
        valor = datos.get('precision_metros')
        if valor not in (None, ''):
            try:
                datos['precision_metros'] = str(round(float(valor)))
            except (TypeError, ValueError):
                pass
        for campo in ('latitud', 'longitud'):
            valor = datos.get(campo)
            if valor not in (None, ''):
                try:
                    datos[campo] = f'{float(valor):.6f}'
                except (TypeError, ValueError):
                    pass
            elif campo in datos:
                datos[campo] = None
        return super().to_internal_value(datos)


class MotivoSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=500)


class AutorizarSerializer(MotivoSerializer):
    consumo = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0, required=False, allow_null=True)


class CorregirSerializer(MotivoSerializer):
    lectura_actual = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0)
