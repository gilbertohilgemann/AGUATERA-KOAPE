"""
Organización territorial de cada institución: zonas y barrios.

Decisión (20/10/2026): cada barrio pertenece a UNA zona; la conexión se ubica en un barrio y su zona
sale del barrio. Los nombres no son la clave: cada zona y barrio tiene su `Code` único en la institución (ver comun/codigos.py).
No se borran: se desactivan (archivan) y siguen visibles en las consultas históricas.
"""
from django.core.validators import RegexValidator
from django.db import models

from comun.codigos import campo_code
from comun.modelos import ModeloInstitucional

COLOR = RegexValidator(r'^#[0-9A-Fa-f]{6}$', 'Use un color en formato #RRGGBB.')


class Zona(ModeloInstitucional):
    Code = campo_code()
    nombre = models.CharField('nombre', max_length=120)
    color = models.CharField('color en el mapa', max_length=7, default='#EA284E', validators=[COLOR])
    poligono = models.JSONField('polígono (GeoJSON)', null=True, blank=True)
    observaciones = models.TextField('observaciones', blank=True)
    activa = models.BooleanField('activa', default=True)

    class Meta:
        verbose_name = 'zona'
        verbose_name_plural = 'zonas'
        ordering = ['nombre']
        constraints = [models.UniqueConstraint(fields=['institucion', 'Code'], name='zona_code_unico')]

    def __str__(self):
        return f'{self.Code} · {self.nombre}'


class Barrio(ModeloInstitucional):
    zona = models.ForeignKey(Zona, on_delete=models.PROTECT, related_name='barrios', verbose_name='zona')
    Code = campo_code()
    nombre = models.CharField('nombre', max_length=120)
    poligono = models.JSONField('polígono (GeoJSON)', null=True, blank=True)
    observaciones = models.TextField('observaciones', blank=True)
    activo = models.BooleanField('activo', default=True)

    class Meta:
        verbose_name = 'barrio'
        verbose_name_plural = 'barrios'
        ordering = ['nombre']
        constraints = [models.UniqueConstraint(fields=['institucion', 'Code'], name='barrio_code_unico')]

    def __str__(self):
        return f'{self.Code} · {self.nombre}'
