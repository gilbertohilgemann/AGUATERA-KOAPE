"""
Capa desacoplada de factura electrónica (sección 11.2): ElectronicInvoiceProvider / Adapter.

No hay ningún proveedor real programado todavía: la especificación prohíbe inventar URLs, endpoints, formatos o
respuestas (D35). Cuando la institución elija su proveedor y tengamos su documentación técnica, se programa un
adaptador que implemente `Adaptador` y se registra con `registrar_adaptador('codigo', Clase)`.

Reglas del flujo (las aplica `servicios.py`, no el adaptador):
- La solicitud se registra (y se confirma en la base) ANTES de llamar al proveedor.
- Cada solicitud tiene un `id_solicitud` único que se envía siempre igual: sirve de clave de idempotencia.
- Un corte o timeout deja la solicitud en «Estado desconocido»: no se vuelve a emitir a ciegas, se CONSULTA.
- Una respuesta HTTP exitosa no alcanza: el adaptador decide el estado según las reglas documentadas del proveedor.
"""
from dataclasses import dataclass, field


class ErrorTemporal(Exception):
    """Timeout o corte: no se sabe si el proveedor recibió el documento (→ estado desconocido)."""


class ErrorProveedor(Exception):
    """El proveedor respondió con un error recuperable (ej. servicio caído): se puede reintentar."""


@dataclass
class Resultado:
    estado: str  # uno de SolicitudElectronica.Estado (enviada, en_proceso, aprobada, rechazada)
    numero_proveedor: str = ''
    cdc: str = ''
    respuesta: dict = field(default_factory=dict)  # lo que se guarda (sin credenciales)
    mensaje: str = ''


class Adaptador:
    """Interfaz que implementa cada proveedor."""

    def __init__(self, proveedor, credenciales: dict):
        self.proveedor = proveedor
        self.credenciales = credenciales

    def enviar(self, id_solicitud: str, documento: dict) -> Resultado:  # pragma: no cover - interfaz
        raise NotImplementedError

    def consultar(self, id_solicitud: str, numero_proveedor: str) -> Resultado:  # pragma: no cover - interfaz
        raise NotImplementedError


_ADAPTADORES: dict[str, type[Adaptador]] = {}


def registrar_adaptador(codigo: str, clase: type[Adaptador]) -> None:
    _ADAPTADORES[codigo] = clase


def quitar_adaptador(codigo: str) -> None:
    _ADAPTADORES.pop(codigo, None)


def adaptador_para(proveedor) -> Adaptador | None:
    from comun.cifrado import descifrar
    import json

    clase = _ADAPTADORES.get(proveedor.adaptador)
    if clase is None:
        return None
    credenciales = json.loads(descifrar(proveedor.credenciales) or '{}') if proveedor.credenciales else {}
    return clase(proveedor, credenciales)


def documento_de(factura) -> dict:
    """Datos de la factura en un formato NEUTRO (cada adaptador lo traduce al formato de su proveedor)."""
    institucion = factura.institucion
    return {
        'emisor': {'ruc': institucion.ruc, 'nombre': institucion.nombre, 'direccion': institucion.direccion},
        'establecimiento': factura.punto.establecimiento, 'punto': factura.punto.punto, 'numero': factura.SerNr,
        'timbrado': factura.timbrado, 'fecha_emision': factura.fecha_emision.isoformat(),
        'condicion': factura.condicion,
        'fecha_vencimiento': factura.fecha_vencimiento.isoformat() if factura.fecha_vencimiento else None,
        'receptor': {'nombre': factura.cliente_nombre, 'documento': factura.cliente_documento,
                     'direccion': factura.cliente_direccion},
        'items': [{'descripcion': l.descripcion, 'cantidad': str(l.cantidad), 'precio_unitario': str(l.precio_unitario),
                   'iva': l.iva, 'importe': str(l.importe), 'importe_iva': str(l.importe_iva),
                   'total': str(l.total_linea)} for l in factura.lineas.all()],
        'totales': {'exento': str(factura.subtotal_exento), 'gravado5': str(factura.subtotal_iva5),
                    'gravado10': str(factura.subtotal_iva10), 'iva5': str(factura.iva5), 'iva10': str(factura.iva10),
                    'total': str(factura.total)},
        'moneda': 'PYG',
    }
