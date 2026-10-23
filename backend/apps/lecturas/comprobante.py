"""
Comprobante de lectura en PDF (sección 9.2, paso 8). Tamaño A6 vertical: entra en una impresora térmica de
80 mm escalado o en una hoja común. No es una factura ni un recibo: lo dice en el propio comprobante.
"""
import io
from zoneinfo import ZoneInfo

from django.utils import timezone

from comun import archivos_privados


def _numero(valor, unidad=''):
    if valor is None:
        return '—'
    texto = f'{valor:,.3f}'.rstrip('0').rstrip('.').replace(',', 'X').replace('.', ',').replace('X', '.')
    return f'{texto} {unidad}'.strip()


def generar_pdf(lectura) -> bytes:
    from reportlab.lib.pagesizes import A6
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    institucion = lectura.institucion
    zona = ZoneInfo(institucion.zona_horaria or 'America/Asuncion')
    capturada = timezone.localtime(lectura.capturada_en, zona)
    ancho, alto = A6
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A6)
    c.setTitle(f'Comprobante de lectura {lectura.comprobante}')
    margen, y = 8 * mm, alto - 10 * mm

    def linea(texto, tamano=8, negrita=False, sangria=0):
        nonlocal y
        c.setFont('Helvetica-Bold' if negrita else 'Helvetica', tamano)
        c.drawString(margen + sangria, y, str(texto)[:70])
        y -= tamano + 3

    def par(etiqueta, valor):
        nonlocal y
        c.setFont('Helvetica', 7.5)
        c.drawString(margen, y, etiqueta)
        c.setFont('Helvetica-Bold', 7.5)
        c.drawRightString(ancho - margen, y, str(valor)[:48])
        y -= 10.5

    linea(institucion.nombre, 10, True)
    if institucion.ruc:
        linea(f'RUC {institucion.ruc}', 7)
    y -= 2
    linea('COMPROBANTE DE LECTURA', 9, True)
    linea(f'{lectura.comprobante} · Período {lectura.periodo}', 8)
    c.line(margen, y + 4, ancho - margen, y + 4)
    y -= 4
    conexion = lectura.conexion
    par('Titular', conexion.cliente.nombre)
    par('Dirección', conexion.direccion or '—')
    par('Conexión', conexion.Code)
    par('Medidor', lectura.medidor.Code)
    unidad = 'm³' if lectura.medidor.unidad == 'm3' else lectura.medidor.unidad
    par(f'Lectura anterior ({lectura.fecha_lectura_anterior:%d/%m/%Y})', _numero(lectura.lectura_anterior))
    par('Lectura actual', _numero(lectura.lectura_actual))
    par('Consumo', _numero(lectura.consumo, unidad) if lectura.consumo is not None else 'pendiente de revisión')
    par('Fecha y hora', capturada.strftime('%d/%m/%Y %H:%M'))
    par('Cobrador', lectura.cobrador.get_full_name() or lectura.cobrador.nombre_usuario)
    par('Estado', lectura.get_estado_display())

    principal = lectura.fotos.filter(principal=True).first()
    if principal is not None:
        try:
            imagen = ImageReader(str(archivos_privados.ruta_absoluta(institucion, principal.archivo)))
            ancho_img, alto_img = imagen.getSize()
            disponible_alto = y - 22 * mm
            escala = min((ancho - 2 * margen) / ancho_img, disponible_alto / alto_img)
            if escala > 0:
                w, h = ancho_img * escala, alto_img * escala
                c.drawImage(imagen, (ancho - w) / 2, y - h - 2, w, h, preserveAspectRatio=True)
                y -= h + 6
        except Exception:  # noqa: BLE001 — sin la foto el comprobante igual sirve
            pass

    c.setFont('Helvetica', 6)
    c.drawString(margen, 15 * mm, 'Este comprobante registra una lectura del medidor.')
    c.drawString(margen, 15 * mm - 8, 'No es una factura ni un recibo de pago.')
    c.drawString(margen, 7 * mm, f'Koape Aguateras · emitido {timezone.localtime(timezone.now(), zona):%d/%m/%Y %H:%M}')
    c.showPage()
    c.save()
    return buffer.getvalue()
