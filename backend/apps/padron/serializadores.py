"""
Serializadores del padrón. Ningún registro se expone por su id interno: los maestros se identifican y
se referencian por su `Code` (comun/codigos.py), con consultas YA filtradas por la institución de la
sesión (un código de otra institución responde «no existe»).
"""
from rest_framework import serializers

from apps.tarifas.models import Tarifa
from apps.territorio.models import Barrio
from comun.codigos import CodeSerializerField, ReferenciaPorCode

from .models import Cliente, Conexion, InstalacionMedidor, Medidor, TitularidadConexion


# --- Clientes ----------------------------------------------------------------------------------

class ClienteSerializer(serializers.ModelSerializer):
    estado_nombre = serializers.CharField(source='get_estado_display', read_only=True)
    cantidad_conexiones = serializers.IntegerField(read_only=True, default=0)
    Code = CodeSerializerField()

    class Meta:
        model = Cliente
        fields = ['Code', 'nombre', 'tipo_persona', 'documento', 'telefono', 'correo', 'direccion_referencia',
                  'observaciones', 'estado', 'estado_nombre', 'fecha_alta', 'cantidad_conexiones', 'creado_en',
                  'actualizado_en']
        read_only_fields = ['fecha_alta', 'creado_en', 'actualizado_en']

    def validate_estado(self, valor):
        if self.instance is None and valor == Cliente.Estado.ARCHIVADO:
            raise serializers.ValidationError('Un cliente nuevo no puede nacer archivado.')
        return valor


class ClienteBreveSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = ['Code', 'nombre', 'documento', 'estado']


# --- Medidores ---------------------------------------------------------------------------------

class MedidorSerializer(serializers.ModelSerializer):
    Code = CodeSerializerField()
    estado_nombre = serializers.CharField(source='get_estado_display', read_only=True)
    conexion_actual = serializers.SerializerMethodField()

    class Meta:
        model = Medidor
        fields = ['Code', 'numero', 'marca', 'modelo', 'unidad', 'lectura_maxima', 'estado', 'estado_nombre',
                  'observaciones', 'conexion_actual', 'creado_en']
        read_only_fields = ['creado_en']

    def get_conexion_actual(self, medidor):
        vigentes = [i for i in medidor.instalaciones.all() if i.fecha_retiro is None]
        if not vigentes:
            return None
        return vigentes[0].conexion.Code

    def validate_lectura_maxima(self, valor):
        if valor is not None and valor <= 0:
            raise serializers.ValidationError('Debe ser mayor que cero.')
        return valor


class InstalacionSerializer(serializers.ModelSerializer):
    medidor = serializers.CharField(source='medidor.Code', read_only=True)
    medidor_numero = serializers.CharField(source='medidor.numero', read_only=True)
    conexion = serializers.CharField(source='conexion.Code', read_only=True)
    instalado_por_nombre = serializers.SerializerMethodField()
    retirado_por_nombre = serializers.SerializerMethodField()

    class Meta:
        model = InstalacionMedidor
        fields = ['conexion', 'medidor', 'medidor_numero', 'fecha_instalacion',
                  'lectura_inicial', 'fecha_retiro', 'lectura_retiro', 'motivo_retiro', 'instalado_por_nombre',
                  'retirado_por_nombre', 'observaciones']

    def get_instalado_por_nombre(self, i):
        return i.instalado_por.get_full_name() if i.instalado_por else ''

    def get_retirado_por_nombre(self, i):
        return i.retirado_por.get_full_name() if i.retirado_por else ''


# --- Conexiones --------------------------------------------------------------------------------

class ConexionListaSerializer(serializers.ModelSerializer):
    cliente = serializers.CharField(source='cliente.Code', read_only=True)
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)
    barrio = serializers.CharField(source='barrio.Code', read_only=True, default=None)
    barrio_nombre = serializers.CharField(source='barrio.nombre', read_only=True, default='')
    zona = serializers.CharField(source='barrio.zona.Code', read_only=True, default=None)
    zona_nombre = serializers.CharField(source='barrio.zona.nombre', read_only=True, default='')
    estado_nombre = serializers.CharField(source='get_estado_display', read_only=True)
    medidor_actual = serializers.SerializerMethodField()
    medidor_numero = serializers.SerializerMethodField()

    class Meta:
        model = Conexion
        fields = ['Code', 'cliente', 'cliente_nombre', 'direccion', 'barrio', 'barrio_nombre',
                  'zona', 'zona_nombre', 'latitud', 'longitud', 'estado', 'estado_nombre', 'medidor_actual',
                  'medidor_numero']

    def _vigente(self, conexion):
        vigentes = getattr(conexion, 'instalaciones_vigentes', None)
        if vigentes is None:
            vigentes = [i for i in conexion.instalaciones.all() if i.fecha_retiro is None]
        return vigentes[0].medidor if vigentes else None

    def get_medidor_actual(self, conexion):
        medidor = self._vigente(conexion)
        return medidor.Code if medidor else None

    def get_medidor_numero(self, conexion):
        medidor = self._vigente(conexion)
        return medidor.numero if medidor else ''


class TitularidadSerializer(serializers.ModelSerializer):
    cliente = serializers.CharField(source='cliente.Code', read_only=True)
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)

    class Meta:
        model = TitularidadConexion
        fields = ['cliente', 'cliente_nombre', 'desde', 'hasta', 'motivo']


class ConexionDetalleSerializer(ConexionListaSerializer):
    tarifa = serializers.CharField(source='tarifa.Code', read_only=True, default=None)
    tarifa_nombre = serializers.CharField(source='tarifa.nombre', read_only=True, default='')
    tiene_foto_vivienda = serializers.SerializerMethodField()
    instalaciones = InstalacionSerializer(many=True, read_only=True)
    titularidades = TitularidadSerializer(many=True, read_only=True)
    metodo_ubicacion_nombre = serializers.CharField(source='get_metodo_ubicacion_display', read_only=True)
    transiciones = serializers.SerializerMethodField()

    class Meta(ConexionListaSerializer.Meta):
        fields = ConexionListaSerializer.Meta.fields + [
            'tarifa', 'tarifa_nombre', 'metodo_ubicacion', 'metodo_ubicacion_nombre', 'precision_metros', 'fecha_instalacion', 'observaciones',
            'tiene_foto_vivienda', 'instalaciones', 'titularidades', 'transiciones', 'creado_en', 'actualizado_en',
        ]

    def get_tiene_foto_vivienda(self, conexion) -> bool:
        return bool(conexion.foto_vivienda)

    def get_transiciones(self, conexion):
        from .servicios import TRANSICIONES
        return [{'estado': e, 'nombre': Conexion.Estado(e).label} for e in sorted(TRANSICIONES.get(conexion.estado, ()))]


class _CamposConexion(serializers.Serializer):
    direccion = serializers.CharField(max_length=255, required=False, allow_blank=True)
    barrio = ReferenciaPorCode(Barrio, required=False, allow_null=True)
    tarifa = ReferenciaPorCode(Tarifa, required=False, allow_null=True)
    latitud = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitud = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    metodo_ubicacion = serializers.ChoiceField(choices=Conexion.MetodoUbicacion.choices, required=False)
    precision_metros = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    fecha_instalacion = serializers.DateField(required=False, allow_null=True)
    observaciones = serializers.CharField(required=False, allow_blank=True)


class ConexionAltaSerializer(_CamposConexion):
    cliente = ReferenciaPorCode(Cliente)
    Code = CodeSerializerField()
    estado = serializers.ChoiceField(choices=Conexion.Estado.choices, required=False)


class ConexionEdicionSerializer(_CamposConexion):
    # Se acepta el mismo Code (ej. un formulario que reenvía todo); otro Code responde 400.
    Code = CodeSerializerField(required=False)


class CambioEstadoSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=Conexion.Estado.choices)
    motivo = serializers.CharField(max_length=500)


class CambioTitularSerializer(serializers.Serializer):
    cliente = ReferenciaPorCode(Cliente)
    desde = serializers.DateField()
    motivo = serializers.CharField(max_length=255)


class InstalarSerializer(serializers.Serializer):
    medidor = ReferenciaPorCode(Medidor)
    fecha = serializers.DateField()
    lectura_inicial = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0)
    observaciones = serializers.CharField(required=False, allow_blank=True, default='')


ESTADOS_RETIRO = [(e, Medidor.Estado(e).label) for e in ('retirado', 'danado', 'baja', 'disponible')]


class RetirarSerializer(serializers.Serializer):
    fecha = serializers.DateField()
    lectura_retiro = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0)
    motivo = serializers.CharField(max_length=255)
    estado_medidor = serializers.ChoiceField(choices=ESTADOS_RETIRO, default='retirado')
    aceptar_lectura_menor = serializers.BooleanField(default=False)


class SustituirSerializer(serializers.Serializer):
    medidor = ReferenciaPorCode(Medidor)
    fecha = serializers.DateField()
    lectura_retiro = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0)
    lectura_inicial = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0)
    motivo = serializers.CharField(max_length=255)
    estado_medidor_retirado = serializers.ChoiceField(choices=ESTADOS_RETIRO, default='retirado')
    aceptar_lectura_menor = serializers.BooleanField(default=False)
