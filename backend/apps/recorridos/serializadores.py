"""Recorridos en la API: por `Code`; cobradores por nombre de usuario; conexiones por su `Code`."""
from rest_framework import serializers

from apps.padron.models import Conexion
from apps.territorio.models import Barrio, Zona
from comun.codigos import CodeSerializerField, ReferenciaPorCode

from .models import Recorrido, PERIODO


class RecorridoSerializer(serializers.ModelSerializer):
    Code = CodeSerializerField()
    periodo = serializers.CharField(max_length=7, validators=[PERIODO])
    estado_nombre = serializers.CharField(source='get_estado_display', read_only=True)
    cobradores = serializers.SerializerMethodField()
    avance = serializers.SerializerMethodField()

    class Meta:
        model = Recorrido
        fields = ['Code', 'nombre', 'periodo', 'estado', 'estado_nombre', 'fecha_desde', 'fecha_hasta', 'observaciones',
                  'cobradores', 'avance']
        read_only_fields = ['estado']

    def get_cobradores(self, recorrido):
        return [{'usuario': a.cobrador.nombre_usuario, 'nombre': a.cobrador.get_full_name() or a.cobrador.nombre_usuario,
                 'activa': a.activa, 'iniciado_en': a.iniciado_en, 'finalizado_en': a.finalizado_en}
                for a in recorrido.asignaciones.all()]

    def get_avance(self, recorrido):
        from .servicios import avance
        return avance(recorrido)

    def validate(self, datos):
        desde, hasta = datos.get('fecha_desde'), datos.get('fecha_hasta')
        if self.instance is not None:
            desde = datos.get('fecha_desde', self.instance.fecha_desde)
            hasta = datos.get('fecha_hasta', self.instance.fecha_hasta)
        if desde and hasta and hasta < desde:
            raise serializers.ValidationError({'fecha_hasta': 'Termina antes de empezar.'})
        return datos


class AgregarConexionesSerializer(serializers.Serializer):
    zona = ReferenciaPorCode(Zona, required=False, allow_null=True)
    barrio = ReferenciaPorCode(Barrio, required=False, allow_null=True)
    conexiones = serializers.ListField(child=ReferenciaPorCode(Conexion), required=False, max_length=5000)

    def validate(self, datos):
        elegidos = [k for k in ('zona', 'barrio', 'conexiones') if datos.get(k)]
        if len(elegidos) != 1:
            raise serializers.ValidationError('Indique una zona, un barrio o una lista de conexiones (solo uno).')
        return datos


class CobradorSerializer(serializers.Serializer):
    usuario = serializers.CharField(max_length=150)


class EstadoSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=Recorrido.Estado.choices)
    motivo = serializers.CharField(max_length=500, required=False, allow_blank=True, default='')
