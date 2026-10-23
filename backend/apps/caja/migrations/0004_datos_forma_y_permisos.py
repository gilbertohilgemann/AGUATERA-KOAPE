"""Sesiones existentes: fija la forma del saldo inicial. Roles existentes que ya cobraban (facturar o cobrar recibos)
reciben `caja.operar`: desde la Fase 7 sin caja abierta no se cobra, y sin el permiso no podrían abrirla."""
from django.db import migrations


def aplicar(apps, schema_editor):
    SesionCaja = apps.get_model('caja', 'SesionCaja')
    FormaPago = apps.get_model('cobranzas', 'FormaPago')
    Permiso = apps.get_model('identidad', 'Permiso')
    Rol = apps.get_model('identidad', 'Rol')
    for sesion in SesionCaja.objects.filter(forma_inicial__isnull=True):
        sesion.forma_inicial = (FormaPago.objects.filter(institucion_id=sesion.institucion_id, tipo='efectivo')
                                .order_by('-activa', 'orden', 'pk').first())
        sesion.save(update_fields=['forma_inicial'])
    operar, _ = Permiso.objects.get_or_create(codigo='caja.operar', defaults={
        'descripcion': 'Abrir y cerrar su propia caja (necesario para cobrar)', 'modulo': 'Caja y gastos', 'vigente': True})
    for rol in Rol.objects.filter(permisos__codigo__in=['facturacion.emitir', 'cobranzas.registrar']).distinct():
        rol.permisos.add(operar)


class Migration(migrations.Migration):
    dependencies = [('caja', '0003_forma_inicial'), ('identidad', '0002_rol_code')]
    operations = [migrations.RunPython(aplicar, migrations.RunPython.noop)]
