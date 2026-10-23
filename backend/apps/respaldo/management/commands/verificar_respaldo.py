"""Revisa un respaldo sin restaurarlo. Uso: python manage.py verificar_respaldo <archivo.zip>"""
from django.core.management.base import BaseCommand, CommandError

from apps.respaldo.restauracion import verificar


class Command(BaseCommand):
    help = 'Verifica un respaldo (ZIP íntegro, base legible, versión compatible) sin restaurarlo.'

    def add_arguments(self, parser):
        parser.add_argument('archivo')

    def handle(self, *args, archivo, **opciones):
        informe = verificar(archivo)
        m = informe['manifiesto']
        self.stdout.write(f'Generado: {m.get("generado_en", "?")}   Motor: {m.get("motor", "?")}   Archivos de código: {informe["archivos"]}')
        base = informe['base'] or {}
        if base.get('motor') == 'sqlite':
            self.stdout.write(f'  Base: integridad {base["integridad"]}, {base["tablas"]} tablas, {base["migraciones"]} migraciones')
        elif base:
            self.stdout.write(f'  Base: volcado PostgreSQL de {base["tamano"]} bytes')
        for aviso in informe['avisos']:
            self.stdout.write(self.style.WARNING(f'  Aviso: {aviso}'))
        if informe['errores']:
            for error in informe['errores']:
                self.stderr.write(self.style.ERROR(f'  ✗ {error}'))
            raise CommandError('El respaldo NO se puede restaurar.')
        self.stdout.write(self.style.SUCCESS('  ✓ Respaldo correcto: se puede restaurar.'))
