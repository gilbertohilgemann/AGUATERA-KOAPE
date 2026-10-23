"""Tarifas y liquidaciones en la API: tarifas por `Code`, versiones por su período, liquidaciones por su número."""
from rest_framework import serializers

from apps.recorridos.models import PERIODO
from comun.codigos import CodeSerializerField

from .models import ConceptoTarifa, Iva, LineaLiquidacion, Liquidacion, Tarifa, VersionTarifa


class ConceptoSerializer(serializers.ModelSerializer):
    tipo_nombre = serializers.CharField(source='get_tipo_display', read_only=True)
    iva_nombre = serializers.CharField(source='get_iva_display', read_only=True)

    class Meta:
        model = ConceptoTarifa
        fields = ['orden', 'nombre', 'tipo', 'tipo_nombre', 'cantidad', 'desde', 'hasta', 'precio', 'porcentaje', 'iva',
                  'iva_nombre']


class ConceptoEntradaSerializer(serializers.Serializer):
    orden = serializers.IntegerField(min_value=0, max_value=32767, required=False, default=0)
    nombre = serializers.CharField(max_length=120)
    tipo = serializers.ChoiceField(choices=ConceptoTarifa.Tipo.choices)
    cantidad = serializers.DecimalField(max_digits=12, decimal_places=3, required=False, allow_null=True)
    desde = serializers.DecimalField(max_digits=12, decimal_places=3, required=False, allow_null=True)
    hasta = serializers.DecimalField(max_digits=12, decimal_places=3, required=False, allow_null=True)
    precio = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    porcentaje = serializers.DecimalField(max_digits=6, decimal_places=3, required=False, allow_null=True)
    iva = serializers.ChoiceField(choices=Iva.choices)


class VersionSerializer(serializers.ModelSerializer):
    conceptos = ConceptoSerializer(many=True, read_only=True)
    usada = serializers.SerializerMethodField()

    class Meta:
        model = VersionTarifa
        fields = ['vigente_desde', 'observaciones', 'conceptos', 'usada']

    def get_usada(self, v) -> bool:
        return v.liquidaciones.exists()


class VersionEntradaSerializer(serializers.Serializer):
    vigente_desde = serializers.CharField(max_length=7, validators=[PERIODO])
    observaciones = serializers.CharField(required=False, allow_blank=True, default='')
    conceptos = ConceptoEntradaSerializer(many=True)


class TarifaSerializer(serializers.ModelSerializer):
    Code = CodeSerializerField()
    versiones = VersionSerializer(many=True, read_only=True)
    cantidad_conexiones = serializers.SerializerMethodField()

    class Meta:
        model = Tarifa
        fields = ['Code', 'nombre', 'descripcion', 'por_defecto', 'activa', 'versiones', 'cantidad_conexiones']

    def get_cantidad_conexiones(self, t) -> int:
        return t.conexiones.count()


class SimularSerializer(serializers.Serializer):
    periodo = serializers.CharField(max_length=7, validators=[PERIODO])
    consumo = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0)


class LineaSerializer(serializers.ModelSerializer):
    iva_nombre = serializers.CharField(source='get_iva_display', read_only=True)

    class Meta:
        model = LineaLiquidacion
        fields = ['concepto', 'tipo', 'cantidad', 'precio', 'importe', 'iva', 'iva_nombre']


class LiquidacionSerializer(serializers.ModelSerializer):
    lectura = serializers.CharField(source='lectura.comprobante')
    conexion = serializers.CharField(source='conexion.Code')
    titular = serializers.CharField(source='conexion.cliente.nombre')
    tarifa = serializers.CharField(source='tarifa.Code')
    tarifa_nombre = serializers.CharField(source='tarifa.nombre')
    version = serializers.CharField(source='version.vigente_desde')
    estado_nombre = serializers.CharField(source='get_estado_display')
    anulada_por = serializers.CharField(source='anulada_por.nombre_usuario', default=None)
    lineas = LineaSerializer(many=True, read_only=True)

    class Meta:
        model = Liquidacion
        fields = ['numero', 'lectura', 'conexion', 'titular', 'periodo', 'tarifa', 'tarifa_nombre', 'version', 'consumo',
                  'subtotal_exento', 'subtotal_iva5', 'subtotal_iva10', 'iva5', 'iva10', 'total', 'estado',
                  'estado_nombre', 'motivo_anulacion', 'anulada_por', 'anulada_en', 'creado_en', 'lineas']
        read_only_fields = fields
