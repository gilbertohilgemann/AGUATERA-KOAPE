from pathlib import Path

from rest_framework import serializers

from apps.cobranzas.models import FormaPago
from comun.codigos import CodeSerializerField, ReferenciaPorCode

from .models import AdjuntoGasto, Caja, CategoriaGasto, Gasto, MovimientoCaja, SesionCaja


class _MaestroSerializer(serializers.ModelSerializer):
    Code = CodeSerializerField()

    def validate_Code(self, valor):
        modelo = self.Meta.model
        if self.instance is None and modelo.objects.de(self.context['institucion']).filter(Code=valor).exists():
            raise serializers.ValidationError('Ya existe otro registro con ese código.')
        return valor


class CajaSerializer(_MaestroSerializer):
    abierta_por = serializers.SerializerMethodField()

    class Meta:
        model = Caja
        fields = ['Code', 'nombre', 'activa', 'abierta_por']

    def get_abierta_por(self, caja):
        sesion = caja.sesiones.filter(estado='abierta').select_related('responsable').first()
        return sesion.responsable.nombre_usuario if sesion else None


class CategoriaGastoSerializer(_MaestroSerializer):
    class Meta:
        model = CategoriaGasto
        fields = ['Code', 'nombre', 'activa']


class MovimientoSerializer(serializers.ModelSerializer):
    forma_pago = serializers.CharField(source='forma_pago.nombre')
    tipo_forma = serializers.CharField(source='forma_pago.tipo')
    origen_nombre = serializers.CharField(source='get_origen_display')
    usuario = serializers.CharField(source='usuario.nombre_usuario', default=None)
    pago = serializers.CharField(source='pago.referencia', default=None)
    recibo = serializers.SerializerMethodField()
    gasto = serializers.CharField(source='gasto.referencia', default=None)
    revertido = serializers.SerializerMethodField()

    class Meta:
        model = MovimientoCaja
        fields = ['fecha_hora', 'tipo', 'origen', 'origen_nombre', 'forma_pago', 'tipo_forma', 'importe',
                  'descripcion', 'usuario', 'pago', 'recibo', 'gasto', 'revertido']

    def get_recibo(self, m):
        recibo = getattr(m.pago, 'recibo', None) if m.pago_id else None
        return recibo.numero_impreso if recibo else None

    def get_revertido(self, m):
        return hasattr(m, 'reversion')


class SesionSerializer(serializers.ModelSerializer):
    caja = serializers.CharField(source='caja.Code')
    caja_nombre = serializers.CharField(source='caja.nombre')
    responsable = serializers.CharField(source='responsable.nombre_usuario')
    estado_nombre = serializers.CharField(source='get_estado_display')
    revisada_por = serializers.CharField(source='revisada_por.nombre_usuario', default=None)
    resumen = serializers.SerializerMethodField()
    declaraciones = serializers.SerializerMethodField()

    class Meta:
        model = SesionCaja
        fields = ['referencia', 'caja', 'caja_nombre', 'responsable', 'abierta_en', 'saldo_inicial', 'estado',
                  'estado_nombre', 'cerrada_en', 'observaciones_cierre', 'revisada_por', 'revisada_en',
                  'comentario_revision', 'resumen', 'declaraciones']

    def get_resumen(self, s):
        from .servicios import resumen
        return [{**f, **{k: f'{f[k]:.2f}' for k in ('saldo_inicial', 'ingresos', 'egresos', 'esperado')}}
                for f in resumen(s)]

    def get_declaraciones(self, s):
        return [{'forma_pago': d.forma_pago.Code, 'nombre': d.forma_pago.nombre, 'esperado': f'{d.esperado:.2f}',
                 'declarado': f'{d.declarado:.2f}', 'diferencia': f'{d.diferencia:.2f}'}
                for d in s.declaraciones.select_related('forma_pago').order_by('forma_pago__orden', 'pk')]


class GastoSerializer(serializers.ModelSerializer):
    categoria = ReferenciaPorCode(CategoriaGasto)
    forma_pago = ReferenciaPorCode(FormaPago)
    categoria_nombre = serializers.CharField(source='categoria.nombre', read_only=True)
    forma_pago_nombre = serializers.CharField(source='forma_pago.nombre', read_only=True)
    estado_nombre = serializers.CharField(source='get_estado_display', read_only=True)
    sesion = serializers.CharField(source='sesion.referencia', default=None, read_only=True)
    registrado_por = serializers.CharField(source='registrado_por.nombre_usuario', read_only=True)
    confirmado_por = serializers.CharField(source='confirmado_por.nombre_usuario', default=None, read_only=True)
    anulado_por = serializers.CharField(source='anulado_por.nombre_usuario', default=None, read_only=True)
    boleta = serializers.SerializerMethodField()
    adjuntos = serializers.SerializerMethodField()

    class Meta:
        model = Gasto
        fields = ['referencia', 'fecha', 'motivo', 'importe', 'categoria', 'categoria_nombre', 'forma_pago',
                  'forma_pago_nombre', 'numero_comprobante', 'beneficiario', 'responsable', 'observaciones', 'sesion',
                  'estado', 'estado_nombre', 'registrado_por', 'creado_en', 'confirmado_por', 'confirmado_en',
                  'anulado_por', 'anulado_en', 'motivo_anulacion', 'boleta', 'adjuntos']
        read_only_fields = ['referencia', 'sesion', 'estado', 'creado_en', 'confirmado_en', 'anulado_en',
                            'motivo_anulacion']
        extra_kwargs = {'importe': {'max_digits': 18, 'decimal_places': 2}}

    def get_boleta(self, g):
        boleta = getattr(g, 'boleta', None)
        return {'numero': boleta.numero_impreso, 'fecha': boleta.fecha} if boleta else None

    def get_adjuntos(self, g):
        return [{'codigo': Path(a.archivo).stem, 'tipo': a.tipo, 'tipo_nombre': a.get_tipo_display(),
                 'es_pdf': a.archivo.endswith('.pdf'), 'subido_por': a.subido_por.nombre_usuario,
                 'creado_en': a.creado_en} for a in g.adjuntos.all()]


def adjunto_por_codigo(gasto, codigo: str) -> AdjuntoGasto | None:
    for adjunto in gasto.adjuntos.all():
        if Path(adjunto.archivo).stem == codigo:
            return adjunto
    return None
