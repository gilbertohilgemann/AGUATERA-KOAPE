from django.db import models


class ManualPlataforma(models.Model):
    """Sin tabla: entrada «Manual de usuario» en el menú del admin de la plataforma."""

    class Meta:
        managed = False
        default_permissions = ('view',)
        verbose_name = 'manual de usuario'
        verbose_name_plural = 'manual de usuario'
