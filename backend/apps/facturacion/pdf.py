"""
PDF de la factura autoimpresa (sección 11.3). Formato A4 con los datos de uso general en Paraguay: emisor y timbrado
con su vigencia, número 001-001-0000001, fecha, condición de venta, cliente, líneas con columnas exentas / 5 % / 10 %
(IVA incluido), liquidación del IVA y total. Los requisitos definitivos (Decreto 6539 art. 19 y modificaciones, y la
autorización de autoimpresor de cada institución) deben verificarse con el contador antes del uso fiscal (D36).
Una factura electrónica NO usa este PDF: su representación (KuDE) la entrega el proveedor.
"""
import io
from decimal import Decimal

from django.utils import timezone


def _gs(valor) -> str:
    if valor is None or valor == '':
        return ''
    return f'{Decimal(valor):,.0f}'.replace(',', '.')


def _num(valor) -> str:
    texto = f'{Decimal(valor):,.3f}'.rstrip('0').rstrip('.')
    return texto.replace(',', 'X').replace('.', ',').replace('X', '.')


def generar_pdf(factura) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    institucion = factura.institucion
    ancho, alto = A4
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f'Factura {factura.numero_impreso}')
    m = 14 * mm

    def texto(x, y, valor, tamano=9, negrita=False, derecha=False):
        c.setFont('Helvetica-Bold' if negrita else 'Helvetica', tamano)
        (c.drawRightString if derecha else c.drawString)(x, y, str(valor))

    # Encabezado: emisor (izquierda) y timbrado/número (derecha)
    y = alto - m
    texto(m, y - 4, institucion.nombre[:60], 13, True)
    texto(m, y - 18, f'RUC: {institucion.ruc or "—"}', 9)
    texto(m, y - 30, (institucion.direccion or '')[:70], 8)
    texto(m, y - 41, f'Tel.: {institucion.telefono}' if institucion.telefono else '', 8)
    caja_x, caja_w = ancho - m - 80 * mm, 80 * mm
    c.rect(caja_x, y - 52, caja_w, 52)
    texto(caja_x + 4, y - 12, f'TIMBRADO N° {factura.timbrado}', 9, True)
    vigencia = ''
    if factura.timbrado_vigencia_desde or factura.timbrado_vigencia_hasta:
        desde = factura.timbrado_vigencia_desde.strftime('%d/%m/%Y') if factura.timbrado_vigencia_desde else '—'
        hasta = factura.timbrado_vigencia_hasta.strftime('%d/%m/%Y') if factura.timbrado_vigencia_hasta else '—'
        vigencia = f'Vigencia: {desde} al {hasta}'
    texto(caja_x + 4, y - 23, vigencia, 8)
    texto(caja_x + 4, y - 36, 'FACTURA', 11, True)
    texto(caja_x + caja_w - 4, y - 36, f'N° {factura.numero_impreso}', 11, True, derecha=True)
    texto(caja_x + 4, y - 47, f'RUC {institucion.ruc or "—"}', 7)
    def marca_anulada():
        if factura.estado == 'anulada':
            c.saveState()
            c.setFont('Helvetica-Bold', 60)
            c.setFillColorRGB(0.85, 0.1, 0.2)
            c.translate(ancho / 2, alto / 2)
            c.rotate(30)
            c.drawCentredString(0, 0, 'ANULADA')
            c.restoreState()

    marca_anulada()

    # Datos de la operación y del cliente
    y -= 70
    c.rect(m, y - 40, ancho - 2 * m, 44)
    texto(m + 4, y - 8, f'Fecha de emisión: {factura.fecha_emision:%d/%m/%Y}', 9)
    condicion = 'Contado' if factura.condicion == 'contado' else 'Crédito'
    texto(ancho / 2, y - 8, f'Condición de venta: {condicion}', 9, True)
    if factura.fecha_vencimiento:
        texto(ancho - m - 4, y - 8, f'Vence: {factura.fecha_vencimiento:%d/%m/%Y}', 9, True, derecha=True)
    texto(m + 4, y - 21, f'Nombre o razón social: {factura.cliente_nombre}'[:95], 9)
    texto(m + 4, y - 33, f'RUC / C.I.: {factura.cliente_documento or "—"}', 9)
    texto(ancho / 2, y - 33, f'Dirección: {factura.cliente_direccion or "—"}'[:60], 9)

    # Detalle
    def titulos(y):
        c.setFillColorRGB(0.93, 0.93, 0.93)
        c.rect(m, y - 4, ancho - 2 * m, 14, fill=1, stroke=0)
        c.setFillColorRGB(0, 0, 0)
        texto(m + 2, y, 'Cant.', 8, True)
        texto(m + 18 * mm, y, 'Descripción', 8, True)
        for x, titulo in ((m + 128 * mm - 2, 'Precio unit.'), (m + 150 * mm - 2, 'Exentas'),
                          (m + 170 * mm - 2, '5 %'), (ancho - m - 2, '10 %')):
            texto(x, y, titulo, 8, True, derecha=True)
        return y - 14

    y = titulos(y - 56)
    for linea in factura.lineas.all():
        if y < 70 * mm:
            c.showPage()
            marca_anulada()
            texto(m, alto - m, f'Factura N° {factura.numero_impreso} (continuación)', 9, True)
            y = titulos(alto - m - 20)
        precio_con_iva = linea.precio_unitario if linea.iva == 'exento' else (
            linea.precio_unitario * (Decimal('1.10') if linea.iva == '10' else Decimal('1.05')))
        con_cantidad = linea.tipo != 'porcentaje'  # en un porcentaje (ej. ERSSAN) la «cantidad» es la base en Gs.
        texto(m + 2, y, _num(linea.cantidad) if con_cantidad else '', 8)
        texto(m + 18 * mm, y, linea.descripcion[:58], 8)
        texto(m + 128 * mm - 2, y, _gs(precio_con_iva.quantize(Decimal('1'))) if con_cantidad else '', 8, derecha=True)
        valores = {'exento': '', '5': '', '10': ''}
        valores[linea.iva] = _gs(linea.total_linea)
        texto(m + 150 * mm - 2, y, valores['exento'], 8, derecha=True)
        texto(m + 170 * mm - 2, y, valores['5'], 8, derecha=True)
        texto(ancho - m - 2, y, valores['10'], 8, derecha=True)
        y -= 12

    # Totales y liquidación del IVA
    y = max(y - 6, 50 * mm)
    c.line(m, y + 8, ancho - m, y + 8)
    texto(m, y - 2, 'Subtotales', 8, True)
    texto(m + 150 * mm - 2, y - 2, _gs(factura.subtotal_exento), 8, derecha=True)
    texto(m + 170 * mm - 2, y - 2, _gs(factura.subtotal_iva5), 8, derecha=True)
    texto(ancho - m - 2, y - 2, _gs(factura.subtotal_iva10), 8, derecha=True)
    texto(m, y - 18, 'TOTAL A PAGAR (Gs.)', 11, True)
    texto(ancho - m - 2, y - 18, _gs(factura.total), 12, True, derecha=True)
    texto(m, y - 34, f'Liquidación del IVA:   (5 %) {_gs(factura.iva5)}   (10 %) {_gs(factura.iva10)}   '
                     f'Total IVA: {_gs(factura.iva5 + factura.iva10)}', 9)
    if factura.observaciones:
        texto(m, y - 48, f'Observaciones: {factura.observaciones}'[:110], 8)
    c.setFont('Helvetica', 7)
    c.drawString(m, 12 * mm, 'ORIGINAL: Cliente')
    c.drawRightString(ancho - m, 12 * mm, f'Koape Aguateras · ref. {factura.referencia} · impreso '
                                           f'{timezone.localtime():%d/%m/%Y %H:%M}')
    c.showPage()
    c.save()
    return buffer.getvalue()
