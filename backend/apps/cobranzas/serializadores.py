from rest_framework import serializers

from apps.facturacion.models import Factura
from apps.padron.models import Cliente
from comun.codigos import CodeSerializerField, ReferenciaPorCode, normalizar_code

from .models import FormaPago, Pago, Recibo


class FormaPagoSerializer(serializers.ModelSerializer):
    Code = CodeSerializerField()
    tipo_nombre = serializers.CharField(source='get_tipo_display', read_only=True)

    class Meta:
        model = FormaPago
        fields = ['Code', 'nombre', 'tipo', 'tipo_nombre', 'requiere_referencia', 'orden', 'activa']

    def validate_Code(self, valor):
        institucion = self.context['institucion']
        if self.instance is None and FormaPago.objects.de(institucion).filter(Code=valor).exists():
            raise serializers.ValidationError('Ya existe una forma de pago con ese código.')
        return valor


class AplicacionSerializer(serializers.Serializer):
    factura = serializers.CharField(max_length=20)
    importe = serializers.DecimalField(max_digits=18, decimal_places=2)


class EmitirReciboSerializer(serializers.Serializer):
    cliente = ReferenciaPorCode(Cliente)
    importe = serializers.DecimalField(max_digits=18, decimal_places=2)
    forma_pago = ReferenciaPorCode(FormaPago)
    referencia_externa = serializers.CharField(required=False, allow_blank=True, default='', max_length=100)
    observaciones = serializers.CharField(required=False, allow_blank=True, default='', max_length=500)
    clave = serializers.CharField(max_length=64)
    aplicaciones = AplicacionSerializer(many=True, required=False, default=list)

    def validate(self, datos):
        institucion = self.context['institucion']
        pares = []
        for a in datos['aplicaciones']:
            factura = Factura.objects.de(institucion).filter(referencia=normalizar_code(a['factura'])).first()
            if factura is None:
                raise serializers.ValidationError({'aplicaciones': f'No existe la factura {a["factura"]}.'})
            pares.append((factura, a['importe']))
        datos['aplicaciones'] = pares
        return datos


def _aplicaciones(pago):
    return [{'factura': a.factura.referencia, 'numero': a.factura.numero_impreso,
             'fecha_emision': a.factura.fecha_emision, 'fecha_vencimiento': a.factura.fecha_vencimiento,
             'total': str(a.factura.total), 'saldo_anterior': str(a.saldo_anterior), 'importe': str(a.importe),
             'saldo_posterior': str(a.saldo_anterior - a.importe), 'estado': a.estado}
            for a in pago.aplicaciones.all()]


class ReciboSerializer(serializers.ModelSerializer):
    numero = serializers.CharField(source='numero_impreso')
    cliente = serializers.CharField(source='cliente.Code')
    forma_pago = serializers.CharField(source='pago.forma_pago.nombre')
    referencia_externa = serializers.CharField(source='pago.referencia_externa')
    observaciones = serializers.CharField(source='pago.observaciones')
    cobrado_por = serializers.CharField(source='pago.usuario.nombre_usuario')
    estado_nombre = serializers.CharField(source='get_estado_display')
    anulado_por = serializers.CharField(source='anulado_por.nombre_usuario', default=None)
    aplicaciones = serializers.SerializerMethodField()

    class Meta:
        model = Recibo
        fields = ['numero', 'fecha_hora', 'cliente', 'cliente_nombre', 'cliente_documento', 'importe', 'forma_pago',
                  'referencia_externa', 'observaciones', 'cobrado_por', 'saldo_restante', 'estado', 'estado_nombre',
                  'anulado_por', 'anulado_en', 'motivo_anulacion', 'aplicaciones']
        read_only_fields = fields

    def get_aplicaciones(self, r):
        return _aplicaciones(r.pago)


class PagoSerializer(serializers.ModelSerializer):
    """Historial de cobranzas: contado y recibos, confirmados y revertidos."""

    cliente = serializers.CharField(source='cliente.Code')
    cliente_nombre = serializers.CharField(source='cliente.nombre')
    forma_pago = serializers.CharField(source='forma_pago.nombre')
    tipo_forma = serializers.CharField(source='forma_pago.tipo')
    origen_nombre = serializers.CharField(source='get_origen_display')
    estado_nombre = serializers.CharField(source='get_estado_display')
    cobrado_por = serializers.CharField(source='usuario.nombre_usuario')
    recibo = serializers.SerializerMethodField()
    aplicaciones = serializers.SerializerMethodField()

    class Meta:
        model = Pago
        fields = ['referencia', 'fecha_hora', 'cliente', 'cliente_nombre', 'importe', 'forma_pago', 'tipo_forma',
                  'referencia_externa', 'origen', 'origen_nombre', 'estado', 'estado_nombre', 'cobrado_por',
                  'motivo_reversion', 'recibo', 'aplicaciones']
        read_only_fields = fields

    def get_recibo(self, p):
        recibo = getattr(p, 'recibo', None)
        return recibo.numero_impreso if recibo else None

    def get_aplicaciones(self, p):
        return _aplicaciones(p)
