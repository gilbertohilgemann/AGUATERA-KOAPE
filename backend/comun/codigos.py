"""
Convención de claves (Convenciones de Proyecto, 20/10/2026):

- Cada registro maestro o de cabecera (clientes, conexiones, medidores, zonas, barrios, artículos…)
  tiene un campo de texto `Code`, único en la institución y SIEMPRE cargado por el usuario.
- El autonumérico interno (`id` de la base) y los numeradores internos (`Secuencia`) nunca se muestran
  ni se aceptan desde la interfaz: la API identifica cada maestro por su `Code` (rutas, referencias y
  filtros) y la auditoría también lo registra por su `Code`.
- Los documentos de formulario continuo (facturas, notas de crédito) llevan `SerNr`, tomado de los
  rangos configurados por punto de expedición (ver `apps.facturacion`).

El `Code` se guarda en mayúsculas (así «c-1» y «C-1» no conviven) y no se cambia después del alta:
la historia (auditoría, documentos impresos, rutas guardadas) lo usa como referencia.
"""
import re

from django.core.validators import RegexValidator
from django.db import models
from rest_framework import serializers

LARGO_CODE = 40
PATRON_CODE = r'[A-Z0-9][A-Z0-9._-]*'
# Para las rutas de la API: se aceptan minúsculas y se normalizan al buscar.
PATRON_RUTA_CODE = r'[A-Za-z0-9][A-Za-z0-9._-]*'
MENSAJE_CODE = 'Use letras, números, puntos, guiones o guiones bajos (sin espacios), empezando por letra o número.'

validar_code = RegexValidator(rf'^{PATRON_CODE}$', MENSAJE_CODE)


def normalizar_code(valor) -> str:
    return str(valor or '').strip().upper()


def code_valido(valor) -> str:
    """Normaliza y valida un `Code` en los servicios (por si se los llama sin pasar por la API)."""
    from comun.errores import ErrorNegocio

    code = normalizar_code(valor)
    if not code:
        raise ErrorNegocio('Cargue el código.')
    if len(code) > LARGO_CODE or not re.fullmatch(PATRON_CODE, code):
        raise ErrorNegocio(f'Código inválido. {MENSAJE_CODE}')
    return code


def campo_code(etiqueta='código'):
    """Campo `Code` de un modelo maestro (la unicidad por institución la declara cada modelo)."""
    return models.CharField(etiqueta, max_length=LARGO_CODE, validators=[validar_code],
                            help_text='Clave del registro, la carga el usuario. No se cambia después del alta.')


class CodeSerializerField(serializers.CharField):
    """`Code` en la API: obligatorio al crear, normalizado y validado; no se acepta un cambio."""

    def __init__(self, **kwargs):
        kwargs.setdefault('max_length', LARGO_CODE)
        super().__init__(**kwargs)

    def to_internal_value(self, dato):
        valor = normalizar_code(super().to_internal_value(dato))
        if not valor:
            raise serializers.ValidationError('Cargue el código.')
        if not re.fullmatch(PATRON_CODE, valor):
            raise serializers.ValidationError(MENSAJE_CODE)
        instancia = getattr(self.parent, 'instance', None)
        if instancia is not None and not isinstance(instancia, (list, tuple)) and valor != instancia.Code:
            raise serializers.ValidationError('El código no se cambia después del alta.')
        return valor


class ReferenciaPorCode(serializers.SlugRelatedField):
    """
    Referencia a otro maestro por su `Code` (nunca por el id interno). La consulta se limita a la
    institución de la sesión: un código de otra institución responde «no existe».
    """

    def __init__(self, modelo, **kwargs):
        self.modelo = modelo
        kwargs.setdefault('queryset', modelo.objects.none())
        super().__init__(slug_field='Code', **kwargs)

    def get_queryset(self):
        return self.modelo.objects.de(self.context.get('institucion'))

    def to_internal_value(self, dato):
        return super().to_internal_value(normalizar_code(dato))

    default_error_messages = {
        'does_not_exist': 'No existe un registro con el código {value}.',
        'invalid': 'Código inválido.',
    }


class VistaPorCode:
    """
    Mixin de vistas: el detalle se busca por `Code` en la ruta (`/clientes/C-001/`), no por el id.
    Debe ir ANTES del ViewSet en la herencia.
    """

    lookup_field = 'Code'
    lookup_url_kwarg = 'Code'
    lookup_value_regex = PATRON_RUTA_CODE

    def get_object(self):
        if self.lookup_url_kwarg in self.kwargs:
            self.kwargs[self.lookup_url_kwarg] = normalizar_code(self.kwargs[self.lookup_url_kwarg])
        return super().get_object()
