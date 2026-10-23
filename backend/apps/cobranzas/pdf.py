"""
PDF del recibo de cobro (sección 11.6): institución, número, fecha y hora, cliente, facturas a las que se aplica (saldo
anterior, aplicado y saldo), importe en números y letras, forma de pago, quién cobró, saldo restante y estado.
El recibo NO reemplaza a la factura fiscal (se aclara en el pie).
"""
import io
from decimal import Decimal

from django.utils import timezone

from .letras import en_letras


def _gs(valor) -> str:
    return f'{Decimal(valor):,.0f}'.replace(',', '.')


def generar_pdf_recibo(recibo) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    institucion = recibo.institucion
    pago = recibo.pago
    ancho, alto = A4
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f'Recibo {recibo.numero_impreso}')
    m = 14 * mm

    def texto(x, y, valor, tamano=9, negrita=False, derecha=False):
        c.setFont('Helvetica-Bold' if negrita else 'Helvetica', tamano)
        (c.drawRightString if derecha else c.drawString)(x, y, str(valor))

    def marca_anulado():
        if recibo.estado == 'anulado':
            c.saveState()
            c.setFont('Helvetica-Bold', 60)
            c.setFillColorRGB(0.85, 0.1, 0.2)
            c.translate(ancho / 2, alto / 2)
            c.rotate(30)
            c.drawCentredString(0, 0, 'ANULADO')
            c.restoreState()

    marca_anulado()
    y = alto - m
    texto(m, y - 4, institucion.nombre[:60], 13, True)
    texto(m, y - 18, f'RUC: {institucion.ruc or "—"}', 9)
    texto(m, y - 30, (institucion.direccion or '')[:70], 8)
    caja_x, caja_w = ancho - m - 70 * mm, 70 * mm
    c.rect(caja_x, y - 40, caja_w, 40)
    texto(caja_x + 4, y - 14, 'RECIBO DE COBRO', 11, True)
    texto(caja_x + caja_w - 4, y - 14, f'N° {recibo.numero_impreso}', 11, True, derecha=True)
    fecha = timezone.localtime(recibo.fecha_hora)
    texto(caja_x + 4, y - 30, f'Fecha: {fecha:%d/%m/%Y %H:%M}', 9)

    y -= 60
    from reportlab.lib.utils import simpleSplit
    letras = simpleSplit(f'La suma de guaraníes: {en_letras(int(recibo.importe))}', 'Helvetica', 9, ancho - 2 * m - 8)
    alto_caja = 54 + 12 * (len(letras) - 1)
    c.rect(m, y - alto_caja + 4, ancho - 2 * m, alto_caja)
    texto(m + 4, y - 8, f'Recibimos de: {recibo.cliente_nombre}'[:90], 10, True)
    texto(m + 4, y - 21, f'RUC / C.I.: {recibo.cliente_documento or "—"}   ·   Cliente {recibo.cliente.Code}', 9)
    for n, linea in enumerate(letras):  # el importe en letras nunca se recorta
        texto(m + 4, y - 34 - 12 * n, linea, 9)
    y -= 12 * (len(letras) - 1)
    forma = pago.forma_pago.nombre + (f' (ref. {pago.referencia_externa})' if pago.referencia_externa else '')
    texto(m + 4, y - 46, f'Forma de pago: {forma}'[:90], 9)
    texto(ancho - m - 4, y - 8, f'Gs. {_gs(recibo.importe)}', 14, True, derecha=True)

    y -= 70
    texto(m, y, 'En concepto de pago de las facturas:', 9, True)
    y -= 16
    columnas = ((m + 2, 'Factura', False), (m + 45 * mm, 'Emisión', False), (m + 70 * mm, 'Vence', False),
                (m + 120 * mm, 'Saldo anterior', True), (m + 150 * mm, 'Aplicado', True), (ancho - m - 2, 'Saldo', True))
    def titulos(y):
        c.setFillColorRGB(0.93, 0.93, 0.93)
        c.rect(m, y - 4, ancho - 2 * m, 14, fill=1, stroke=0)
        c.setFillColorRGB(0, 0, 0)
        for x, titulo, derecha in columnas:
            texto(x, y, titulo, 8, True, derecha=derecha)
        return y - 14

    y = titulos(y)
    for a in pago.aplicaciones.all():
        if y < 50 * mm:
            c.showPage()
            marca_anulado()
            texto(m, alto - m, f'Recibo N° {recibo.numero_impreso} (continuación)', 9, True)
            y = titulos(alto - m - 20)
        f = a.factura
        valores = (f.numero_impreso, f'{f.fecha_emision:%d/%m/%Y}',
                   f'{f.fecha_vencimiento:%d/%m/%Y}' if f.fecha_vencimiento else '—', _gs(a.saldo_anterior),
                   _gs(a.importe), _gs(a.saldo_anterior - a.importe))
        for (x, _, derecha), valor in zip(columnas, valores):
            texto(x, y, valor, 8, derecha=derecha)
        y -= 12

    y = max(y - 10, 40 * mm)
    c.line(m, y + 6, ancho - m, y + 6)
    texto(m, y - 8, f'Total recibido: Gs. {_gs(recibo.importe)}', 10, True)
    texto(ancho - m, y - 8, f'Saldo pendiente del cliente después de este pago: Gs. {_gs(recibo.saldo_restante)}', 9,
          derecha=True)
    texto(m, y - 22, f'Cobrado por: {pago.usuario.nombre or pago.usuario.nombre_usuario}', 9)
    if pago.observaciones:
        texto(m, y - 36, f'Observaciones: {pago.observaciones}'[:110], 8)
    if recibo.estado == 'anulado':
        texto(m, y - 50, f'ANULADO el {timezone.localtime(recibo.anulado_en):%d/%m/%Y %H:%M}: '
                         f'{recibo.motivo_anulacion}'[:110], 9, True)
    c.line(ancho - m - 60 * mm, 28 * mm, ancho - m, 28 * mm)
    texto(ancho - m - 30 * mm - 12, 24 * mm, 'Firma y aclaración', 8)
    c.setFont('Helvetica', 7)
    c.drawString(m, 12 * mm, 'Este recibo no reemplaza a la factura.')
    c.drawRightString(ancho - m, 12 * mm, f'Koape Aguateras · impreso {timezone.localtime():%d/%m/%Y %H:%M}')
    c.showPage()
    c.save()
    return buffer.getvalue()
