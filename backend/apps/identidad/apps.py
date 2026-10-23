from django.apps import AppConfig
from django.db.models.signals import m2m_changed, post_migrate


def _impedir_roles_de_otra_institucion(sender, instance, action, pk_set, **kwargs):
    """
    Defensa en profundidad: aunque una vista se equivoque, la base nunca recibe un rol de otra
    institución asignado a un usuario.
    """
    if action != 'pre_add' or not pk_set:
        return
    from comun.errores import ErrorCruceInstitucion

    from .models import Rol, Usuario

    if isinstance(instance, Usuario):
        ajenos = Rol.objects.filter(pk__in=pk_set).exclude(institucion_id=instance.institucion_id)
    else:  # se agregan usuarios desde el lado del rol
        ajenos = Usuario.objects.filter(pk__in=pk_set).exclude(institucion_id=instance.institucion_id)
    if ajenos.exists():
        raise ErrorCruceInstitucion('No se pueden relacionar registros de instituciones distintas.')


class IdentidadConfig(AppConfig):
    name = 'apps.identidad'
    label = 'identidad'
    verbose_name = 'Usuarios y permisos'

    def ready(self):
        from .catalogo_permisos import sincronizar_tras_migrar
        from .models import Usuario

        post_migrate.connect(sincronizar_tras_migrar, sender=self)
        m2m_changed.connect(_impedir_roles_de_otra_institucion, sender=Usuario.roles.through)
