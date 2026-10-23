"""Instituciones existentes: formas de pago iniciales y el rol CONSULTA puede ver facturas y cobros
(las instituciones nuevas ya los traen)."""
from django.db import migrations

FORMAS = [('EFECTIVO', 'Efectivo', 'efectivo', False, 1), ('TRANSFERENCIA', 'Transferencia', 'transferencia', True, 2),
          ('POS', 'POS (tarjeta)', 'pos', True, 3)]
PERMISOS = [('facturacion.consultar', 'Consultar facturas y descargar su PDF', 'Facturación'),
            ('cobranzas.consultar', 'Consultar pagos, recibos y saldos de los clientes', 'Pagos y recibos')]


def aplicar(apps, schema_editor):
    Institucion = apps.get_model('plataforma', 'Institucion')
    FormaPago = apps.get_model('cobranzas', 'FormaPago')
    Permiso = apps.get_model('identidad', 'Permiso')
    Rol = apps.get_model('identidad', 'Rol')
    for institucion in Institucion.objects.all():
        for code, nombre, tipo, referencia, orden in FORMAS:
            FormaPago.objects.get_or_create(institucion=institucion, Code=code, defaults={
                'nombre': nombre, 'tipo': tipo, 'requiere_referencia': referencia, 'orden': orden})
    permisos = [Permiso.objects.get_or_create(codigo=c, defaults={'descripcion': d, 'modulo': m, 'vigente': True})[0]
                for c, d, m in PERMISOS]
    for rol in Rol.objects.filter(Code='CONSULTA'):
        rol.permisos.add(*permisos)


class Migration(migrations.Migration):
    dependencies = [('cobranzas', '0001_initial'), ('identidad', '0002_rol_code'), ('plataforma', '0005_aplicacion_pagos')]
    operations = [migrations.RunPython(aplicar, migrations.RunPython.noop)]
