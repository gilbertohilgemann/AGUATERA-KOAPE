"""Errores de reglas de negocio: el mensaje se muestra tal cual al usuario (respuesta 400)."""


class ErrorNegocio(Exception):
    """
    Regla de negocio incumplida. `codigo` permite al frontend reaccionar a casos puntuales;
    `datos` viaja junto al mensaje.
    """

    codigo = 'regla_de_negocio'

    def __init__(self, mensaje: str, *, codigo: str | None = None, **datos):
        super().__init__(mensaje)
        if codigo:
            self.codigo = codigo
        self.datos = datos


class ErrorCruceInstitucion(ErrorNegocio):
    """Se intentó relacionar registros de dos instituciones distintas."""

    codigo = 'cruce_de_institucion'
