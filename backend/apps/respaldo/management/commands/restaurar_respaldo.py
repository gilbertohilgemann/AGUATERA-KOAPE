"""
Restaura un respaldo. Detenga el sistema antes (start restaurar <archivo> lo hace solo).

  python manage.py restaurar_respaldo <archivo.zip>            # pregunta antes de pisar
  python manage.py restaurar_respaldo <archivo.zip> --si       # sin preguntar
"""
from django.core.management.base import BaseCommand, CommandError

from apps.respaldo.restauracion import ErrorRestauracion, restaurar, verificar


class Command(BaseCommand):
    help = 'Restaura un respaldo (con verificación y respaldo previo de lo actual).'

    def add_arguments(self, parser):
        parser.add_argument('archivo')
        parser.add_argument('--si', action='store_true', help='No pedir confirmación.')
        parser.add_argument('--sin-respaldo-previo', action='store_true',
                            help='No respaldar lo actual antes de pisarlo (no recomendado).')

    def handle(self, *args, archivo, **opciones):
        informe = verificar(archivo)
        if informe['errores']:
            raise CommandError('El respaldo no pasó la verificación: ' + ' '.join(informe['errores']))
        self.stdout.write(self.style.WARNING(
            f'Se van a reemplazar la base de datos y los archivos subidos por el respaldo del '
            f'{informe["manifiesto"].get("generado_en", "?")}.'))
        if not opciones['si'] and input('Escriba SI para continuar: ').strip().upper() != 'SI':
            raise CommandError('Cancelado: no se cambió nada.')
        try:
            r = restaurar(archivo, respaldo_previo=not opciones['sin_respaldo_previo'])
        except ErrorRestauracion as error:
            raise CommandError(str(error))
        self.stdout.write(self.style.SUCCESS(f'  ✓ Restaurado ({r["archivos"]} archivos subidos).'))
        if r['respaldo_previo']:
            self.stdout.write(f'  Respaldo previo (para deshacer): {r["respaldo_previo"]}')
