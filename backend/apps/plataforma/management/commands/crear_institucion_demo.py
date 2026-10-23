"""
Crea las instituciones de DEMOSTRACIÓN (idempotente): DEMO y DEMO2, cada una con su administrador.

Sirven para probar el sistema y el aislamiento entre instituciones. Usuario «admin», contraseña
Demo.Koape.2026 (al primer ingreso se pide cambiarla).
"""
from django.core.management.base import BaseCommand

from apps.plataforma.models import Institucion
from apps.plataforma.servicios import crear_institucion

DEMOS = [
    ('DEMO', 'Junta de Saneamiento Demostración'),
    ('DEMO2', 'Aguatera Comunitaria Demostración 2'),
]
CONTRASENA = 'Demo.Koape.2026'


class Command(BaseCommand):
    help = 'Crea las instituciones de demostración DEMO y DEMO2.'

    def handle(self, *args, **opciones):
        for codigo, nombre in DEMOS:
            if Institucion.objects.filter(codigo=codigo).exists():
                self.stdout.write(f'  {codigo}: ya existía.')
                continue
            crear_institucion(datos={'codigo': codigo, 'nombre': nombre, 'contacto': 'Institución de demostración'},
                              admin_usuario='admin', admin_contrasena=CONTRASENA, admin_nombre='Administrador demo')
            self.stdout.write(self.style.SUCCESS(f'  {codigo}: creada (usuario admin · contraseña {CONTRASENA}).'))
