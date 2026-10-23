"""Convención de claves (D23): el rol pasa a tener `Code` (único por institución, no cambia)."""
import re

from django.db import migrations, models

import comun.codigos


def completar_codes(apps, schema_editor):
    Rol = apps.get_model('identidad', 'Rol')
    usados = set()
    for rol in Rol.objects.order_by('id'):
        base = re.sub(r'[^A-Z0-9._-]+', '-', rol.nombre.upper()).strip('-._')[:34] or 'ROL'
        code, n = base, 1
        while (rol.institucion_id, code) in usados:
            n += 1
            code = f'{base}-{n}'
        usados.add((rol.institucion_id, code))
        rol.Code = code
        rol.save(update_fields=['Code'])


class Migration(migrations.Migration):
    dependencies = [('identidad', '0001_initial')]

    operations = [
        migrations.AddField(
            model_name='rol', name='Code',
            field=models.CharField(default='', help_text='Clave del registro, la carga el usuario. No se cambia después del alta.',
                                   max_length=40, validators=[comun.codigos.validar_code], verbose_name='código del rol'),
            preserve_default=False,
        ),
        migrations.RunPython(completar_codes, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='rol',
            constraint=models.UniqueConstraint(fields=('institucion', 'Code'), name='rol_code_unico'),
        ),
    ]
