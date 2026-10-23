"""
Ticket de lectura para impresora térmica portátil (58 mm u 80 mm de ancho, largo según el contenido).

Lo que entrega el cobrador después de leer el medidor: datos de la institución y del cliente, la lectura ANTERIOR
(número de comprobante, fecha y valor), la lectura ACTUAL (número, fecha, valor leído y consumo) y los ARANCELES de
la liquidación (conceptos de la tarifa, IVA y total). No es una factura ni un recibo: lo dice el propio ticket.
Una lectura en revisión todavía no tiene aranceles: el ticket lo indica.
"""
import io
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone

ANCHOS = {58: 58, 80: 80}          # mm de papel
MARGEN_MM = 3


def _numero(valor, decimales=3) -> str:
    if valor is None:
        return '—'
    texto = f'{Decimal(valor):,.{decimales}f}'
    if decimales:
        texto = texto.rstrip('0').rstrip('.')
    return texto.replace(',', 'X').replace('.', ',').replace('X', '.')


def _gs(valor) -> str:
    return _numero(Decimal(valor).quantize(Decimal('1')), 0)


def lectura_previa(lectura):
    """La lectura confirmada de la que salió la «lectura anterior» (None si vino de la instalación del medidor)."""
    if lectura.origen_anterior != lectura.OrigenAnterior.LECTURA:
        return None
    from .models import Lectura
    return (Lectura.objects.filter(instalacion=lectura.instalacion, estado=Lectura.Estado.CONFIRMADA,
                                   periodo__lt=lectura.periodo, lectura_actual=lectura.lectura_anterior)
            .order_by('-periodo', '-capturada_en').first())


def contenido(lectura) -> list[tuple]:
    """
    Renglones del ticket: ('titulo', texto) centrado y en negrita · ('texto', texto) centrado · ('par', etiqueta,
    valor) · ('negrita_par', etiqueta, valor) · ('linea',) separador · ('nota', texto) chico.
    """
    institucion = lectura.institucion
    zona = ZoneInfo(institucion.zona_horaria or 'America/Asuncion')
    conexion, cliente, medidor = lectura.conexion, lectura.conexion.cliente, lectura.medidor
    unidad = 'm³' if medidor.unidad == 'm3' else medidor.unidad
    r = [('titulo', institucion.nombre)]
    if institucion.ruc:
        r.append(('texto', f'RUC {institucion.ruc}'))
    if institucion.direccion:
        r.append(('texto', institucion.direccion))
    if institucion.telefono:
        r.append(('texto', f'Tel. {institucion.telefono}'))
    r += [('linea',), ('titulo', 'COMPROBANTE DE LECTURA'), ('texto', f'Período {lectura.periodo}'), ('linea',)]

    r += [('subtitulo', 'CLIENTE'), ('par', 'Nombre', cliente.nombre)]
    if cliente.documento:
        r.append(('par', 'C.I./RUC', cliente.documento))
    r += [('par', 'N.º de cliente', cliente.Code), ('par', 'Conexión', conexion.Code)]
    if conexion.direccion:
        r.append(('par', 'Dirección', conexion.direccion))
    r.append(('par', 'Medidor', f'{medidor.numero} ({medidor.Code})' if medidor.numero else medidor.Code))
    r.append(('linea',))

    previa = lectura_previa(lectura)
    r.append(('subtitulo', 'LECTURA ANTERIOR'))
    if previa is not None:
        r.append(('par', 'N.º', previa.comprobante))
    elif lectura.origen_anterior == lectura.OrigenAnterior.INSTALACION:
        r.append(('par', 'Origen', 'Instalación del medidor'))
    r += [('par', 'Fecha', f'{lectura.fecha_lectura_anterior:%d/%m/%Y}'),
          ('par', 'Lectura', _numero(lectura.lectura_anterior)), ('linea',)]

    capturada = timezone.localtime(lectura.capturada_en, zona)
    r += [('subtitulo', 'LECTURA ACTUAL'), ('par', 'N.º', lectura.comprobante),
          ('par', 'Fecha', capturada.strftime('%d/%m/%Y %H:%M')),
          ('par', 'Lectura', _numero(lectura.lectura_actual)),
          ('negrita_par', 'Consumo', f'{_numero(lectura.consumo)} {unidad}' if lectura.consumo is not None
           else 'en revisión'), ('linea',)]

    liquidacion = lectura.liquidaciones.filter(estado='vigente').prefetch_related('lineas').first()
    r.append(('subtitulo', 'ARANCELES'))
    if liquidacion is None:
        motivo = (f'La lectura quedó en revisión ({(lectura.get_motivo_revision_display() or "").lower()}): los aranceles se '
                  'calculan cuando la oficina la confirme.') if lectura.estado == lectura.Estado.REVISION \
            else 'Sin aranceles calculados para esta lectura.'
        r.append(('nota', motivo))
    else:
        r.append(('nota', f'Liquidación {liquidacion.numero} · tarifa {liquidacion.tarifa.nombre}'))
        for linea in liquidacion.lineas.all():
            if linea.tipo in ('minimo', 'excedente', 'tramo', 'por_m3'):
                detalle = f'{linea.concepto} ({_numero(linea.cantidad)} {unidad} × {_gs(linea.precio)})' \
                    if linea.tipo != 'minimo' else linea.concepto
            elif linea.tipo == 'porcentaje':
                detalle = f'{linea.concepto} ({_numero(linea.precio, 2)} %)'
            else:
                detalle = linea.concepto
            r.append(('par', detalle, _gs(linea.importe)))
        if liquidacion.iva10:
            r.append(('par', 'IVA 10 %', _gs(liquidacion.iva10)))
        if liquidacion.iva5:
            r.append(('par', 'IVA 5 %', _gs(liquidacion.iva5)))
        r.append(('negrita_par', 'TOTAL Gs.', _gs(liquidacion.total)))
    r.append(('linea',))
    cobrador = lectura.cobrador
    r.append(('nota', f'Leído por {cobrador.get_full_name() or cobrador.nombre_usuario}'))
    r.append(('nota', 'Este ticket registra la lectura del medidor. No es una factura ni un recibo de pago.'))
    r.append(('nota', f'Koape Aguateras · {timezone.localtime(timezone.now(), zona):%d/%m/%Y %H:%M}'))
    return r


def generar_ticket(lectura, ancho_mm: int = 58) -> bytes:
    from reportlab.lib.units import mm
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas

    ancho_mm = ANCHOS.get(int(ancho_mm), 58)
    ancho = ancho_mm * mm
    margen = MARGEN_MM * mm
    util = ancho - 2 * margen
    base = 7.5 if ancho_mm == 58 else 9                 # tamaño de letra
    normal, negrita = 'Helvetica', 'Helvetica-Bold'

    # 1) Se arma la lista de renglones ya cortados al ancho, para saber el largo del papel.
    renglones = []                                      # (tipo, fuente, tamaño, texto_izq, texto_der)

    def cortar(texto, fuente, tamano, ancho_disp):
        return simpleSplit(str(texto), fuente, tamano, ancho_disp) or ['']

    def simple(texto):
        # Las letras de las impresoras térmicas (y la Helvetica del PDF) no traen «³» ni «×».
        return str(texto).replace('m³', 'm3').replace('³', '3').replace('×', 'x')

    for item in [tuple(simple(x) for x in i) for i in contenido(lectura)]:
        tipo = item[0]
        if tipo == 'linea':
            renglones.append(('linea', None, base, '', ''))
        elif tipo in ('titulo', 'texto', 'subtitulo', 'nota'):
            fuente = negrita if tipo in ('titulo', 'subtitulo') else normal
            tamano = base + 1.5 if tipo == 'titulo' else base - 1 if tipo == 'nota' else base
            for parte in cortar(item[1], fuente, tamano, util):
                renglones.append((tipo, fuente, tamano, parte, ''))
        else:                                           # par / negrita_par: etiqueta a la izquierda, valor a la derecha
            fuente_valor = negrita
            fuente_etiqueta = negrita if tipo == 'negrita_par' else normal
            tamano = base + (1 if tipo == 'negrita_par' else 0)
            valor = str(item[2])
            ancho_valor = stringWidth(valor, fuente_valor, tamano)
            if ancho_valor > util * 0.6:                # valor largo: etiqueta arriba y valor abajo, a la derecha
                renglones.append(('izq', fuente_etiqueta, tamano, item[1], ''))
                for parte in cortar(valor, fuente_valor, tamano, util):
                    renglones.append(('der', fuente_valor, tamano, '', parte))
            else:
                partes = cortar(item[1], fuente_etiqueta, tamano, util - ancho_valor - 2 * mm)
                for n, parte in enumerate(partes):
                    renglones.append(('par', fuente_etiqueta, tamano, parte, valor if n == len(partes) - 1 else ''))

    interlinea = 1.3
    alto = 2 * margen + 4 * mm + sum((r[2] * interlinea) + (2 if r[0] == 'linea' else 0) for r in renglones)

    # 2) Se dibuja.
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(ancho, alto))
    c.setTitle(f'Ticket de lectura {lectura.comprobante}')
    y = alto - margen - base
    for tipo, fuente, tamano, izq, der in renglones:
        if tipo == 'linea':
            c.setDash(1, 1.5)
            c.line(margen, y + tamano * 0.4, ancho - margen, y + tamano * 0.4)
            c.setDash()
            y -= tamano * interlinea + 2
            continue
        c.setFont(fuente, tamano)
        if tipo in ('titulo', 'texto', 'subtitulo'):
            c.drawCentredString(ancho / 2, y, izq)
        elif tipo in ('nota', 'izq'):
            c.drawString(margen, y, izq)
        elif tipo == 'der':
            c.drawRightString(ancho - margen, y, der)
        else:
            c.drawString(margen, y, izq)
            if der:
                c.setFont(negrita, tamano)
                c.drawRightString(ancho - margen, y, der)
        y -= tamano * interlinea
    c.showPage()
    c.save()
    return buffer.getvalue()
