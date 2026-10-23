"""
Los roles iniciales de las instituciones existentes reciben los permisos nuevos de la Fase 3:
COBRADOR → tomar lecturas; CONSULTA → consultar lecturas. (Las instituciones nuevas ya los traen.)
"""
from django.db import migrations

NUEVOS = {
    'lecturas.registrar': ('Tomar lecturas en los recorridos asignados (aplicación del cobrador)', 'COBRADOR'),
    'lecturas.consultar': ('Consultar lecturas, sus fotos y comprobantes', 'CONSULTA'),
}


def asignar(apps, schema_editor):
    Permiso = apps.get_model('identidad', 'Permiso')
    Rol = apps.get_model('identidad', 'Rol')
    for codigo, (descripcion, rol_code) in NUEVOS.items():
        permiso, _ = Permiso.objects.get_or_create(
            codigo=codigo, defaults={'descripcion': descripcion, 'modulo': 'Recorridos y lecturas', 'vigente': True})
        for rol in Rol.objects.filter(Code=rol_code):
            rol.permisos.add(permiso)


class Migration(migrations.Migration):
    dependencies = [('lecturas', '0002_initial'), ('identidad', '0002_rol_code')]

    operations = [migrations.RunPython(asignar, migrations.RunPython.noop)]
