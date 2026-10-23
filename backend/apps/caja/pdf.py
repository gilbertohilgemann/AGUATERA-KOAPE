"""PDF de la boleta interna de gasto (sección 14.1) y del arqueo de una sesión de caja (sección 13.1)."""
import io
from decimal import Decimal

from django.utils import timezone

from apps.cobranzas.letras import en_letras


def _gs(valor) -> str:
    return f'{Decimal(valor):,.0f}'.replace(',', '.')


def _lienzo(titulo):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(titulo)
    return buffer, c, A4


def _escritor(c):
    def texto(x, y, valor, tamano=9, negrita=False, derecha=False):
        c.setFont('Helvetica-Bold' if negrita else 'Helvetica', tamano)
        (c.drawRightString if derecha else c.drawString)(x, y, str(valor))
    return texto


def _encabezado(c, texto, institucion, ancho, alto, m, titulo, numero, subtitulo):
    y = alto - m
    texto(m, y - 4, institucion.nombre[:60], 13, True)
    texto(m, y - 18, f'RUC: {institucion.ruc or "—"}', 9)
    texto(m, y - 30, (institucion.direccion or '')[:70], 8)
    from reportlab.lib.units import mm
    caja_x, caja_w = ancho - m - 78 * mm, 78 * mm
    c.rect(caja_x, y - 40, caja_w, 40)
    texto(caja_x + 4, y - 14, titulo, 10, True)
    texto(caja_x + caja_w - 4, y - 14, numero, 10, True, derecha=True)
    texto(caja_x + 4, y - 30, subtitulo, 9)
    return y - 60


def pdf_boleta(boleta) -> bytes:
    """Boleta para imprimir y FIRMAR cuando el gasto no tiene comprobante. Evidencia administrativa interna."""
    from reportlab.lib.units import mm
    from reportlab.lib.utils import simpleSplit
    gasto = boleta.gasto
    buffer, c, (ancho, alto) = _lienzo(f'Boleta interna {boleta.numero_impreso}')
    texto = _escritor(c)
    m = 14 * mm
    y = _encabezado(c, texto, boleta.institucion, ancho, alto, m, 'BOLETA INTERNA DE GASTO', f'N° {boleta.numero_impreso}',
                    f'Fecha: {boleta.fecha:%d/%m/%Y}')
    if gasto.estado == 'anulado':
        c.saveState()
        c.setFont('Helvetica-Bold', 60)
        c.setFillColorRGB(0.85, 0.1, 0.2)
        c.translate(ancho / 2, alto / 2)
        c.rotate(30)
        c.drawCentredString(0, 0, 'ANULADO')
        c.restoreState()
    texto(m, y, f'Pagado a: {boleta.beneficiario}'[:90], 11, True)
    texto(ancho - m, y, f'Gs. {_gs(boleta.importe)}', 14, True, derecha=True)
    y -= 18
    for linea in simpleSplit(f'La suma de guaraníes: {en_letras(int(boleta.importe))}', 'Helvetica', 10, ancho - 2 * m):
        texto(m, y, linea, 10)
        y -= 14
    y -= 4
    for linea in simpleSplit(f'En concepto de: {boleta.motivo}', 'Helvetica', 10, ancho - 2 * m):
        texto(m, y, linea, 10)
        y -= 14
    texto(m, y, f'Categoría: {gasto.categoria.nombre}   ·   Forma de pago: {gasto.forma_pago.nombre}   ·   '
                f'Referencia {gasto.referencia}', 9)
    y -= 14
    texto(m, y, f'Responsable: {boleta.responsable or "—"}', 9)
    # Firmas
    y -= 70
    for x, rotulo in ((m, 'Firma del beneficiario (recibí conforme)'), (ancho / 2 + 10 * mm, 'Firma del responsable')):
        c.line(x, y, x + 75 * mm, y)
        texto(x, y - 12, rotulo, 8)
        texto(x, y - 24, 'Aclaración y C.I.:', 8)
    c.setFont('Helvetica-Oblique', 8)
    c.drawString(m, y - 60, 'Documento interno de respaldo administrativo. NO sustituye a un comprobante fiscal.')
    c.setFont('Helvetica', 7)
    c.drawRightString(ancho - m, 12 * mm, f'Koape Aguateras · impreso {timezone.localtime():%d/%m/%Y %H:%M}')
    c.showPage()
    c.save()
    return buffer.getvalue()


def pdf_sesion(sesion) -> bytes:
    """Arqueo: saldos por forma de pago (esperado, contado, diferencia) y el detalle de movimientos."""
    from reportlab.lib.units import mm

    from .servicios import resumen
    buffer, c, (ancho, alto) = _lienzo(f'Caja {sesion.referencia}')
    texto = _escritor(c)
    m = 14 * mm
    y = _encabezado(c, texto, sesion.institucion, ancho, alto, m, 'ARQUEO DE CAJA', sesion.referencia,
                    f'{sesion.caja.Code} · {sesion.get_estado_display()}'[:45])
    abierta = timezone.localtime(sesion.abierta_en)
    cerrada = timezone.localtime(sesion.cerrada_en) if sesion.cerrada_en else None
    texto(m, y, f'Responsable: {sesion.responsable.nombre or sesion.responsable.nombre_usuario}   ·   '
                f'Apertura: {abierta:%d/%m/%Y %H:%M}   ·   Cierre: {f"{cerrada:%d/%m/%Y %H:%M}" if cerrada else "abierta"}', 9)
    y -= 22
    declaradas = {d.forma_pago.Code: d for d in sesion.declaraciones.select_related('forma_pago')}
    columnas = (m + 2, m + 60 * mm, m + 85 * mm, m + 110 * mm, m + 135 * mm, m + 158 * mm, ancho - m - 2)
    c.setFillColorRGB(0.93, 0.93, 0.93)
    c.rect(m, y - 4, ancho - 2 * m, 14, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)
    for n, titulo in enumerate(('Forma de pago', 'Inicial', 'Ingresos', 'Egresos', 'Esperado', 'Contado', 'Diferencia')):
        texto(columnas[n], y, titulo, 8, True, derecha=n > 0)
    y -= 14
    for fila in resumen(sesion):
        d = declaradas.get(fila['forma_pago'])
        valores = (fila['nombre'], _gs(fila['saldo_inicial']), _gs(fila['ingresos']), _gs(fila['egresos']),
                   _gs(fila['esperado']), _gs(d.declarado) if d else '—', _gs(d.diferencia) if d else '—')
        for n, valor in enumerate(valores):
            texto(columnas[n], y, valor, 8, n == 6 and d is not None and d.diferencia != 0, derecha=n > 0)
        y -= 12
    texto(m, y - 4, 'Cada forma de pago se arquea por separado: transferencias y POS no son dinero en la caja.', 7)
    y -= 26
    texto(m, y, 'Movimientos', 9, True)
    y -= 14
    for mov in sesion.movimientos.select_related('forma_pago').order_by('fecha_hora', 'pk'):
        if y < 40 * mm:
            c.showPage()
            y = alto - m
            texto(m, y, f'Arqueo {sesion.referencia} (continuación)', 9, True)
            y -= 18
        signo = '+' if mov.tipo == 'ingreso' else '-'  # guion ASCII: la fuente estándar no trae U+2212
        texto(m + 2, y, f'{timezone.localtime(mov.fecha_hora):%d/%m %H:%M}', 8)
        texto(m + 25 * mm, y, f'{mov.descripcion}'[:70], 8)
        texto(m + 150 * mm, y, mov.forma_pago.nombre[:16], 8)
        texto(ancho - m - 2, y, f'{signo} {_gs(mov.importe)}', 8, derecha=True)
        y -= 11
    y -= 10
    if sesion.observaciones_cierre:
        texto(m, y, f'Observaciones del cierre: {" ".join(sesion.observaciones_cierre.split())}'[:120], 8)
        y -= 12
    if sesion.comentario_revision:
        for linea in sesion.comentario_revision.splitlines():
            texto(m, y, f'Revisión: {linea}'[:120], 8)
            y -= 12
    y = max(y - 50, 25 * mm)
    for x, rotulo in ((m, 'Firma del cajero'), (ancho / 2 + 10 * mm, 'Firma del supervisor')):
        c.line(x, y, x + 75 * mm, y)
        texto(x, y - 12, rotulo, 8)
    c.setFont('Helvetica', 7)
    c.drawRightString(ancho - m, 12 * mm, f'Koape Aguateras · impreso {timezone.localtime():%d/%m/%Y %H:%M}')
    c.showPage()
    c.save()
    return buffer.getvalue()
