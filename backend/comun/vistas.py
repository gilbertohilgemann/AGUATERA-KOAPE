"""Piezas comunes de las vistas de la API."""
from rest_framework.exceptions import NotAuthenticated


def institucion_de(request):
    """
    Institución de la sesión. La fija la autenticación a partir del token (nunca de un parámetro
    del navegador). Sin institución, la solicitud no se atiende.
    """
    institucion = getattr(request._request if hasattr(request, '_request') else request, 'institucion', None)
    if institucion is None:
        raise NotAuthenticated('Sesión inválida o vencida.')
    return institucion


def entero(valor):
    """Id numérico de un parámetro de consulta; None si no es un entero válido (evita errores 500)."""
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


class VistaInstitucional:
    """
    Mixin para vistas DRF de modelos institucionales.

    La vista declara `modelo` (un `ModeloInstitucional`); la consulta queda limitada a la institución
    de la sesión, así un id de otra institución responde 404 aunque exista.
    """

    modelo = None

    @property
    def institucion(self):
        return institucion_de(self.request)

    def consulta_base(self):
        return self.modelo.objects.de(self.institucion)

    def get_queryset(self):
        return self.consulta_base()
