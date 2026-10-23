from django.db import models


class Respaldo(models.Model):
    """Sin tabla: solo genera la entrada «Backup completo» en el menú del admin."""

    class Meta:
        managed = False
        default_permissions = ('view',)
        verbose_name = 'backup completo'
        verbose_name_plural = 'backup completo'
