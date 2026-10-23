from django.db import models


class MigracionBaseDatos(models.Model):
    """Sin tabla: solo genera la entrada «Migración de base de datos» en el menú del admin."""

    class Meta:
        managed = False
        default_permissions = ('view',)
        verbose_name = 'migración de base de datos'
        verbose_name_plural = 'migración de base de datos'
