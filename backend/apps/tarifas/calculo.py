"""
Motor de cálculo tarifario: una función pura (sin base de datos) que recibe los conceptos de una versión de tarifa
y el consumo, y devuelve las líneas y los totales. La usan el simulador y las liquidaciones; al ser pura, una
liquidación se puede reproducir exactamente a partir de su instantánea (criterio de aceptación de la Fase 4).

Reglas (confirmadas con Koape Sistemas, 21/10/2026):
- Consumo mínimo: los m³ del mínimo a su precio, se usen o no.
- Excedente: cada m³ por encima del mínimo, a un precio fijo por m³.
- Tramos: los m³ de cada tramo a su precio (escalonado: (desde, hasta]).
- Por m³: cada m³ consumido a un precio.
- Cargo fijo: un monto por mes.
- Porcentaje (ej. tasa ERSSAN, Ley 1614 art. 22): % sobre el importe del servicio SIN impuestos ni otras tasas,
  es decir, sobre la suma de los conceptos que no son porcentajes.
- Los precios no incluyen IVA: el IVA se calcula aparte por tasa (10 % y 5 %) sobre los subtotales gravados.
- Guaraníes: cada línea se redondea a entero; el IVA también.
"""
from decimal import ROUND_HALF_UP, Decimal

CERO = Decimal('0')
TIPOS = ('minimo', 'excedente', 'tramo', 'por_m3', 'fijo', 'porcentaje')


def redondear(valor: Decimal) -> Decimal:
    return Decimal(valor).quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def _d(valor) -> Decimal | None:
    return None if valor in (None, '') else Decimal(str(valor))


class ErrorTarifa(ValueError):
    """La configuración de la tarifa no permite calcular (se muestra al usuario)."""


def validar_conceptos(conceptos: list[dict]) -> None:
    """Coherencia de una versión: cada tipo con sus datos, un solo mínimo, excedente solo con mínimo, tramos sin solaparse."""
    minimos = [c for c in conceptos if c['tipo'] == 'minimo']
    if len(minimos) > 1:
        raise ErrorTarifa('Una tarifa tiene a lo sumo un consumo mínimo.')
    tramos = []
    for c in conceptos:
        tipo, nombre = c.get('tipo'), (c.get('nombre') or '').strip()
        if tipo not in TIPOS:
            raise ErrorTarifa(f'Tipo de concepto desconocido: {tipo}.')
        if not nombre:
            raise ErrorTarifa('Cada concepto necesita un nombre (es lo que se ve en la factura).')
        if c.get('iva') not in ('10', '5', 'exento'):
            raise ErrorTarifa(f'«{nombre}»: IVA inválido.')
        precio, porcentaje = _d(c.get('precio')), _d(c.get('porcentaje'))
        if tipo == 'porcentaje':
            if porcentaje is None or not (CERO < porcentaje <= 100):
                raise ErrorTarifa(f'«{nombre}»: indique un porcentaje mayor que 0 y hasta 100.')
        elif precio is None or precio < 0:
            raise ErrorTarifa(f'«{nombre}»: indique el precio (cero o más).')
        if tipo == 'minimo' and (_d(c.get('cantidad')) is None or _d(c.get('cantidad')) <= 0):
            raise ErrorTarifa(f'«{nombre}»: indique los m³ del consumo mínimo.')
        if tipo == 'excedente' and not minimos:
            raise ErrorTarifa(f'«{nombre}»: el excedente necesita un concepto de consumo mínimo.')
        if tipo == 'tramo':
            desde, hasta = _d(c.get('desde')), _d(c.get('hasta'))
            if desde is None or desde < 0 or (hasta is not None and hasta <= desde):
                raise ErrorTarifa(f'«{nombre}»: el tramo necesita «desde» (0 o más) y «hasta» mayor que «desde» (o vacío).')
            tramos.append((desde, hasta, nombre))
    # Un solo modelo de consumo: mínimo + excedente, tramos (con o sin mínimo) o precio por m³. Combinarlos cobraría
    # dos veces los mismos m³ (revisión independiente de la Fase 4).
    cuenta = {t: sum(1 for c in conceptos if c['tipo'] == t) for t in ('excedente', 'por_m3')}
    if cuenta['excedente'] > 1 or cuenta['por_m3'] > 1:
        raise ErrorTarifa('A lo sumo un concepto de excedente y uno de precio por m³.')
    modelos = sum(1 for activo in (cuenta['excedente'] > 0, bool(tramos), cuenta['por_m3'] > 0) if activo)
    if modelos > 1:
        raise ErrorTarifa('Use un solo cálculo del consumo: excedente sobre el mínimo, tramos o precio por m³ (no combinados).')
    if cuenta['por_m3'] and minimos:
        raise ErrorTarifa('El precio por m³ no se combina con un consumo mínimo: use excedente.')
    tramos.sort(key=lambda t: t[0])
    if tramos:
        inicio = _d(minimos[0].get('cantidad')) if minimos else Decimal('0')
        if tramos[0][0] != inicio:
            raise ErrorTarifa(f'El primer tramo debe empezar en {inicio} m³ (donde termina el mínimo, o en 0).')
        for (d1, h1, n1), (d2, _h2, n2) in zip(tramos, tramos[1:]):
            if h1 is None or d2 < h1:
                raise ErrorTarifa(f'Los tramos «{n1}» y «{n2}» se superponen.')
            if d2 > h1:
                raise ErrorTarifa(f'Entre «{n1}» y «{n2}» quedan m³ sin precio: el tramo siguiente debe empezar en {h1}.')
        if tramos[-1][1] is not None:
            raise ErrorTarifa(f'El último tramo («{tramos[-1][2]}») debe quedar sin límite («hasta» vacío).')


def calcular(conceptos: list[dict], consumo) -> dict:
    """
    Devuelve {'lineas': [...], 'subtotal_exento', 'subtotal_iva5', 'subtotal_iva10', 'iva5', 'iva10', 'total'}.
    Cada línea: concepto, tipo, cantidad, precio, importe (sin IVA), iva.
    """
    validar_conceptos(conceptos)
    consumo = Decimal(str(consumo))
    if consumo < 0:
        raise ErrorTarifa('El consumo no puede ser negativo.')
    minimo = next((_d(c['cantidad']) for c in conceptos if c['tipo'] == 'minimo'), None)
    ordenados = sorted(enumerate(conceptos), key=lambda x: (int(x[1].get('orden') or 0), x[0]))
    lineas = []
    for _, c in ordenados:
        tipo, precio = c['tipo'], _d(c.get('precio'))
        if tipo == 'porcentaje':
            continue  # después, sobre la base del servicio
        if tipo == 'minimo':
            cantidad = _d(c['cantidad'])
        elif tipo == 'excedente':
            cantidad = max(CERO, consumo - minimo)
        elif tipo == 'tramo':
            desde, hasta = _d(c['desde']), _d(c.get('hasta'))
            tope = consumo if hasta is None else min(consumo, hasta)
            cantidad = max(CERO, tope - desde)
        elif tipo == 'por_m3':
            cantidad = consumo
        else:  # fijo
            cantidad = Decimal('1')
        lineas.append({'concepto': c['nombre'].strip(), 'tipo': tipo, 'cantidad': cantidad, 'precio': precio,
                       'importe': redondear(cantidad * precio), 'iva': c['iva'], 'orden': len(lineas)})
    base_servicio = sum((l['importe'] for l in lineas), CERO)
    for _, c in ordenados:
        if c['tipo'] != 'porcentaje':
            continue
        porcentaje = _d(c['porcentaje'])
        lineas.append({'concepto': c['nombre'].strip(), 'tipo': 'porcentaje', 'cantidad': base_servicio,
                       'precio': porcentaje, 'importe': redondear(base_servicio * porcentaje / 100), 'iva': c['iva'],
                       'orden': len(lineas)})
    subtotal = {tasa: sum((l['importe'] for l in lineas if l['iva'] == tasa), CERO) for tasa in ('exento', '5', '10')}
    iva5, iva10 = redondear(subtotal['5'] * Decimal('0.05')), redondear(subtotal['10'] * Decimal('0.10'))
    return {
        'lineas': lineas, 'subtotal_exento': subtotal['exento'], 'subtotal_iva5': subtotal['5'],
        'subtotal_iva10': subtotal['10'], 'iva5': iva5, 'iva10': iva10,
        'total': subtotal['exento'] + subtotal['5'] + subtotal['10'] + iva5 + iva10,
    }


def concepto_a_dict(c) -> dict:
    """Instantánea serializable de un ConceptoTarifa (lo que se guarda en la liquidación)."""
    def texto(v):
        return None if v is None else str(v)
    return {'orden': c.orden, 'nombre': c.nombre, 'tipo': c.tipo, 'cantidad': texto(c.cantidad), 'desde': texto(c.desde),
            'hasta': texto(c.hasta), 'precio': texto(c.precio), 'porcentaje': texto(c.porcentaje), 'iva': c.iva}
