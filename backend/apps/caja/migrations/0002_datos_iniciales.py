"""Instituciones existentes: una caja inicial (CAJA1) y las categorías de gasto iniciales."""
from django.db import migrations

CATEGORIAS = [('MANTENIMIENTO', 'Mantenimiento y reparaciones'), ('MATERIALES', 'Materiales'),
              ('COMBUSTIBLE', 'Combustible'), ('SERVICIOS', 'Servicios (energía, internet…)'),
              ('JORNALES', 'Jornales y honorarios'), ('OTROS', 'Otros')]


def aplicar(apps, schema_editor):
    Institucion = apps.get_model('plataforma', 'Institucion')
    Caja = apps.get_model('caja', 'Caja')
    CategoriaGasto = apps.get_model('caja', 'CategoriaGasto')
    for institucion in Institucion.objects.all():
        Caja.objects.get_or_create(institucion=institucion, Code='CAJA1', defaults={'nombre': 'Caja principal'})
        for code, nombre in CATEGORIAS:
            CategoriaGasto.objects.get_or_create(institucion=institucion, Code=code, defaults={'nombre': nombre})


class Migration(migrations.Migration):
    dependencies = [('caja', '0001_initial')]
    operations = [migrations.RunPython(aplicar, migrations.RunPython.noop)]
