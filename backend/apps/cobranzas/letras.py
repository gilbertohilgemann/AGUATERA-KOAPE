"""Importes en letras para el recibo (ej. 44.800 → «cuarenta y cuatro mil ochocientos»)."""

UNIDADES = ['cero', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve', 'diez', 'once', 'doce',
            'trece', 'catorce', 'quince', 'dieciséis', 'diecisiete', 'dieciocho', 'diecinueve', 'veinte', 'veintiuno',
            'veintidós', 'veintitrés', 'veinticuatro', 'veinticinco', 'veintiséis', 'veintisiete', 'veintiocho',
            'veintinueve']
DECENAS = ['', '', '', 'treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa']
CENTENAS = ['', 'ciento', 'doscientos', 'trescientos', 'cuatrocientos', 'quinientos', 'seiscientos', 'setecientos',
            'ochocientos', 'novecientos']


def _hasta_999(n: int) -> str:
    if n == 100:
        return 'cien'
    c, resto = divmod(n, 100)
    partes = [CENTENAS[c]] if c else []
    if resto:
        if resto < 30:
            partes.append(UNIDADES[resto])
        else:
            d, u = divmod(resto, 10)
            partes.append(DECENAS[d] + (f' y {UNIDADES[u]}' if u else ''))
    return ' '.join(partes)


def _apocopar(texto: str) -> str:
    """«uno» delante de «mil»/«millones» → «un»; «veintiuno» → «veintiún»."""
    if texto.endswith('veintiuno'):
        return texto[:-len('veintiuno')] + 'veintiún'
    if texto.endswith('uno'):
        return texto[:-3] + 'un'
    return texto


def en_letras(numero: int) -> str:
    n = int(numero)
    if n == 0:
        return 'cero'
    if n < 0:
        return 'menos ' + en_letras(-n)
    partes = []
    millones, resto = divmod(n, 1_000_000)
    if millones:
        partes.append('un millón' if millones == 1 else f'{_apocopar(en_letras(millones))} millones')
    miles, unidades = divmod(resto, 1000)
    if miles:
        partes.append('mil' if miles == 1 else f'{_apocopar(_hasta_999(miles))} mil')
    if unidades:
        partes.append(_hasta_999(unidades))
    return ' '.join(partes)
