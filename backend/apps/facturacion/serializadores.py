"""
Puntos de expedición y rangos. Se identifican por su `Code`; el contador interno del rango
(`ultimo_usado`) nunca sale en la API: solo se informa si el rango ya se usó o si se agotó.
"""
from rest_framework import serializers

from apps.cobranzas.models import FormaPago
from apps.padron.models import Cliente
from apps.tarifas.models import Liquidacion
from comun.codigos import CodeSerializerField, ReferenciaPorCode

from .models import Factura, LineaFactura, PuntoExpedicion, RangoNumeracion


class RangoSerializer(serializers.ModelSerializer):
    Code = CodeSerializerField()
    punto = ReferenciaPorCode(PuntoExpedicion)
    punto_prefijo = serializers.CharField(source='punto.prefijo', read_only=True)
    tipo_documento_nombre = serializers.CharField(source='get_tipo_documento_display', read_only=True)
    en_uso = serializers.BooleanField(read_only=True)
    agotado = serializers.BooleanField(read_only=True)

    class Meta:
        model = RangoNumeracion
        fields = ['Code', 'punto', 'punto_prefijo', 'tipo_documento', 'tipo_documento_nombre', 'timbrado', 'desde',
                  'hasta', 'vigencia_desde', 'vigencia_hasta', 'activo', 'observaciones', 'en_uso', 'agotado']


class PuntoSerializer(serializers.ModelSerializer):
    Code = CodeSerializerField()
    prefijo = serializers.CharField(read_only=True)
    rangos = serializers.SerializerMethodField()

    class Meta:
        model = PuntoExpedicion
        fields = ['Code', 'establecimiento', 'punto', 'prefijo', 'nombre', 'direccion', 'activo', 'observaciones',
                  'rangos']

    def get_rangos(self, punto):
        return RangoSerializer(punto.rangos.all(), many=True, context=self.context).data


# --- Facturas (Fase 5) ----------------------------------------------------------------------------------




class LineaFacturaSerializer(serializers.ModelSerializer):
    liquidacion = serializers.CharField(source='liquidacion.numero')

    class Meta:
        model = LineaFactura
        fields = ['descripcion', 'tipo', 'cantidad', 'precio_unitario', 'iva', 'importe', 'importe_iva', 'total_linea',
                  'liquidacion']


class FacturaSerializer(serializers.ModelSerializer):
    numero = serializers.CharField(source='numero_impreso')
    punto = serializers.CharField(source='punto.Code')
    cliente = serializers.CharField(source='cliente.Code')
    estado_nombre = serializers.CharField(source='get_estado_display')
    condicion_nombre = serializers.CharField(source='get_condicion_display')
    emitida_por = serializers.CharField(source='emitida_por.nombre_usuario')
    anulada_por = serializers.CharField(source='anulada_por.nombre_usuario', default=None)
    liquidaciones = serializers.SerializerMethodField()
    lineas = LineaFacturaSerializer(many=True, read_only=True)
    electronica = serializers.SerializerMethodField()
    pagado = serializers.SerializerMethodField()
    saldo = serializers.SerializerMethodField()
    estado_cobro = serializers.SerializerMethodField()
    pagos = serializers.SerializerMethodField()

    class Meta:
        model = Factura
        fields = ['referencia', 'numero', 'SerNr', 'punto', 'timbrado', 'timbrado_vigencia_desde', 'timbrado_vigencia_hasta',
                  'modalidad', 'cliente', 'cliente_nombre', 'cliente_documento', 'cliente_direccion', 'condicion',
                  'condicion_nombre', 'fecha_emision', 'fecha_vencimiento', 'subtotal_exento', 'subtotal_iva5',
                  'subtotal_iva10', 'iva5', 'iva10', 'total', 'estado', 'estado_nombre', 'observaciones', 'cdc',
                  'emitida_por', 'creado_en', 'anulada_por', 'anulada_en', 'motivo_anulacion', 'liquidaciones', 'lineas',
                  'electronica', 'pagado', 'saldo', 'estado_cobro', 'pagos']
        read_only_fields = fields

    def _pagado(self, f):
        if not hasattr(f, 'pagado'):
            from apps.cobranzas.servicios import pagado
            f.pagado = pagado(f)
        return f.pagado

    def get_pagado(self, f):
        return f'{self._pagado(f):.2f}'

    def get_saldo(self, f):
        # En trámite (electrónica) todavía no se puede cobrar con recibo: su saldo es el total.
        if f.estado in (Factura.Estado.EMITIDA, Factura.Estado.EN_TRAMITE):
            return f'{f.total - self._pagado(f):.2f}'
        return '0.00'

    def get_estado_cobro(self, f):
        from apps.cobranzas.servicios import estado_cobro
        return estado_cobro(f, f.total - self._pagado(f))

    def get_pagos(self, f):
        """Cobros aplicados a la factura (vigentes y revertidos: la trazabilidad no se pierde)."""
        return [{'pago': a.pago.referencia, 'fecha_hora': a.pago.fecha_hora, 'importe': str(a.importe),
                 'forma_pago': a.pago.forma_pago.nombre, 'referencia_externa': a.pago.referencia_externa,
                 'origen': a.pago.origen, 'recibo': getattr(getattr(a.pago, 'recibo', None), 'numero_impreso', None),
                 'estado': a.estado, 'usuario': a.pago.usuario.nombre_usuario}
                for a in f.aplicaciones_pago.all()]

    def get_liquidaciones(self, f):
        return [{'numero': a.liquidacion.numero, 'periodo': a.liquidacion.periodo, 'conexion': a.liquidacion.conexion.Code,
                 'importe': str(a.importe), 'estado': a.estado} for a in f.asignaciones.all()]

    def get_electronica(self, f):
        solicitud = getattr(f, 'solicitud', None) if f.modalidad == 'electronica' else None
        if solicitud is None:
            return None
        return {'estado': solicitud.estado, 'estado_nombre': solicitud.get_estado_display(), 'intentos': solicitud.intentos,
                'proveedor': solicitud.proveedor.nombre, 'ultimo_error': solicitud.ultimo_error}


class EmitirSerializer(serializers.Serializer):
    cliente = ReferenciaPorCode(Cliente)
    liquidaciones = serializers.ListField(child=serializers.CharField(max_length=12), min_length=1, max_length=200)
    condicion = serializers.ChoiceField(choices=Factura.Condicion.choices)
    punto = ReferenciaPorCode(PuntoExpedicion, required=False, allow_null=True)
    observaciones = serializers.CharField(required=False, allow_blank=True, default='', max_length=500)
    forma_pago = ReferenciaPorCode(FormaPago, required=False, allow_null=True)
    referencia_externa = serializers.CharField(required=False, allow_blank=True, default='', max_length=100)

    def validate_liquidaciones(self, numeros):
        from comun.codigos import normalizar_code
        numeros = list(dict.fromkeys(normalizar_code(n) for n in numeros))
        encontradas = list(Liquidacion.objects.de(self.context.get('institucion')).filter(numero__in=numeros))
        if len(encontradas) != len(numeros):
            raise serializers.ValidationError('Alguna liquidación no existe.')
        return encontradas


class PendienteSerializer(serializers.ModelSerializer):
    conexion = serializers.CharField(source='conexion.Code')
    direccion = serializers.CharField(source='conexion.direccion')
    tarifa = serializers.CharField(source='tarifa.nombre')
    lectura = serializers.CharField(source='lectura.comprobante')

    class Meta:
        model = Liquidacion
        fields = ['numero', 'periodo', 'conexion', 'direccion', 'tarifa', 'lectura', 'consumo', 'total']
