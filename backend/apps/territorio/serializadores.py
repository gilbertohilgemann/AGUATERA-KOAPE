from rest_framework import serializers

from comun.codigos import CodeSerializerField, ReferenciaPorCode
from comun.errores import ErrorNegocio
from comun.geo import validar_poligono

from .models import Barrio, Zona


class PoligonoField(serializers.JSONField):
    def to_internal_value(self, dato):
        valor = super().to_internal_value(dato)
        try:
            return validar_poligono(valor)
        except ErrorNegocio as error:
            raise serializers.ValidationError(str(error))


class ZonaSerializer(serializers.ModelSerializer):
    Code = CodeSerializerField()
    poligono = PoligonoField(required=False, allow_null=True)
    cantidad_barrios = serializers.SerializerMethodField()

    class Meta:
        model = Zona
        fields = ['Code', 'nombre', 'color', 'poligono', 'observaciones', 'activa', 'cantidad_barrios']

    def get_cantidad_barrios(self, zona) -> int:
        return zona.barrios.filter(activo=True).count()

    def validate_Code(self, valor):
        consulta = Zona.objects.de(self.context['institucion']).filter(Code=valor)
        if self.instance is not None:
            consulta = consulta.exclude(pk=self.instance.pk)
        if consulta.exists():
            raise serializers.ValidationError('Ya existe una zona con ese código.')
        return valor


class BarrioSerializer(serializers.ModelSerializer):
    Code = CodeSerializerField()
    poligono = PoligonoField(required=False, allow_null=True)
    zona = ReferenciaPorCode(Zona)
    zona_nombre = serializers.CharField(source='zona.nombre', read_only=True)

    class Meta:
        model = Barrio
        fields = ['Code', 'zona', 'zona_nombre', 'nombre', 'poligono', 'observaciones', 'activo']

    def validate_zona(self, zona):
        cambia = self.instance is None or self.instance.zona_id != zona.pk
        if cambia and not zona.activa:
            raise serializers.ValidationError('La zona está archivada: no se le pueden agregar barrios.')
        return zona

    def validate_Code(self, valor):
        consulta = Barrio.objects.de(self.context['institucion']).filter(Code=valor)
        if self.instance is not None:
            consulta = consulta.exclude(pk=self.instance.pk)
        if consulta.exists():
            raise serializers.ValidationError('Ya existe un barrio con ese código.')
        return valor
