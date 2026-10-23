"""Revisa la configuración de seguridad y los respaldos. Uso: python manage.py verificar_seguridad"""
from django.core.management.base import BaseCommand

from apps.plataforma.seguridad import revisar

MARCA = {'grave': '✗', 'aviso': '!', 'ok': '✓'}


class Command(BaseCommand):
    help = 'Chequeo de seguridad y respaldos de la instalación.'

    def handle(self, *args, **opciones):
        hallazgos = revisar()
        for h in hallazgos:
            estilo = {'grave': self.style.ERROR, 'aviso': self.style.WARNING, 'ok': self.style.SUCCESS}[h['nivel']]
            self.stdout.write(estilo(f'  {MARCA[h["nivel"]]} {h["mensaje"]}'))
            if h['accion']:
                self.stdout.write(f'      → {h["accion"]}')
        graves = sum(1 for h in hallazgos if h['nivel'] == 'grave')
        self.stdout.write(f'Graves: {graves}. Avisos: {sum(1 for h in hallazgos if h["nivel"] == "aviso")}.')
