"""El rol inicial CONSULTA de las instituciones existentes puede ver liquidaciones (las nuevas ya lo traen)."""
from django.db import migrations


def asignar(apps, schema_editor):
    Permiso = apps.get_model('identidad', 'Permiso')
    Rol = apps.get_model('identidad', 'Rol')
    permiso, _ = Permiso.objects.get_or_create(
        codigo='liquidaciones.consultar',
        defaults={'descripcion': 'Consultar liquidaciones e importes', 'modulo': 'Tarifas y liquidaciones', 'vigente': True})
    for rol in Rol.objects.filter(Code='CONSULTA'):
        rol.permisos.add(permiso)


class Migration(migrations.Migration):
    dependencies = [('tarifas', '0001_initial'), ('identidad', '0002_rol_code')]
    operations = [migrations.RunPython(asignar, migrations.RunPython.noop)]
