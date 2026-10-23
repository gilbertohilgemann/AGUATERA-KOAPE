"""
Base de todos los modelos que pertenecen a una institución.

Regla del sistema (D2, una base central): todo registro de negocio lleva su `institucion` y:

1. Se consulta SIEMPRE filtrando por la institución de la sesión (`ConsultaInstitucional.de(institucion)`
   o el mixin `VistaInstitucional`), nunca por un id que mande el navegador.
2. Antes de relacionar dos registros se verifica que sean de la misma institución
   (`validar_misma_institucion`), aunque el usuario conozca los ids de otra.
3. `PROTECT` al borrar la institución: nada desaparece en cascada.
"""
from django.db import models

from .errores import ErrorCruceInstitucion


class ConsultaInstitucional(models.QuerySet):
    def de(self, institucion):
        """Registros de UNA institución. Sin institución no devuelve nada (cerrado por defecto)."""
        if institucion is None:
            return self.none()
        return self.filter(institucion=institucion)


class ModeloInstitucional(models.Model):
    institucion = models.ForeignKey(
        'plataforma.Institucion', on_delete=models.PROTECT, related_name='+', verbose_name='institución',
    )
    creado_en = models.DateTimeField('creado el', auto_now_add=True)
    actualizado_en = models.DateTimeField('actualizado el', auto_now=True)

    objects = ConsultaInstitucional.as_manager()

    class Meta:
        abstract = True


def validar_misma_institucion(institucion, *objetos) -> None:
    """
    Lanza `ErrorCruceInstitucion` si algún objeto pertenece a otra institución.

    Se usa en los servicios antes de vincular registros (ej. asignar un rol a un usuario,
    un medidor a una conexión, un pago a una factura).
    """
    institucion_id = getattr(institucion, 'pk', institucion)
    for objeto in objetos:
        if objeto is None:
            continue
        if getattr(objeto, 'institucion_id', None) != institucion_id:
            raise ErrorCruceInstitucion('No se pueden relacionar registros de instituciones distintas.')
