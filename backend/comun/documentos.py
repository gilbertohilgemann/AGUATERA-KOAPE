"""
Normalización de documentos de identidad (C.I., RUC, DNI, pasaporte) para reconocer a la MISMA persona en distintas
instituciones aunque cada una lo haya cargado distinto: «1.234.567», «1234567» y el RUC «1234567-8» son la misma.

- Se quitan puntos, espacios y guiones y se pasa a mayúsculas.
- Un RUC paraguayo (número + guion + dígito verificador) se reduce al número base, que es la C.I. de la persona.
- `documento_identificable`: los rellenos que se cargan cuando falta el dato («0», «S/N», «000000»…) no identifican a
  nadie y no sirven para el portal.
"""
import re

RUC = re.compile(r'^\s*([0-9][0-9.\s]*)\s*-\s*([0-9])\s*$')


def normalizar_documento(texto) -> str:
    texto = (texto or '').strip().upper()
    if not texto:
        return ''
    ruc = RUC.match(texto)
    if ruc:
        texto = ruc.group(1)
    return re.sub(r'[^0-9A-Z]', '', texto)[:30]


def documento_identificable(normalizado: str) -> bool:
    """Al menos 5 dígitos y no todos iguales (descarta rellenos como «0», «SN», «11111»)."""
    digitos = re.sub(r'[^0-9]', '', normalizado or '')
    return len(digitos) >= 5 and len(set(digitos)) > 1
