"""
Migra la base a PostgreSQL desde la terminal (alternativa al panel, para correr por SSH).

Uso: python manage.py migrate_to_postgres --servidor localhost --puerto 5432 --usuario postgres [--nombre koape_aguateras]
La contraseña se pide por teclado (o se toma de la variable DB_CONTRASENA).
"""
import getpass
import os

from django.core.management.base import BaseCommand, CommandError

from apps.migracion_bd import db_migracion


class Command(BaseCommand):
    help = 'Copia todos los datos de SQLite a PostgreSQL y deja .env apuntando a PostgreSQL.'

    def add_arguments(self, parser):
        parser.add_argument('--servidor', default='localhost')
        parser.add_argument('--puerto', default='5432')
        parser.add_argument('--usuario', default='postgres')
        parser.add_argument('--nombre', default='koape_aguateras')

    def handle(self, *args, **o):
        contrasena = os.environ.get('DB_CONTRASENA') or getpass.getpass('Contraseña de PostgreSQL: ')
        datos = db_migracion.DatosPostgres(servidor=o['servidor'], puerto=o['puerto'], usuario=o['usuario'],
                                           contrasena=contrasena, nombre=o['nombre'])
        try:
            db_migracion.migrar_a_postgres(datos, informar=lambda t: self.stdout.write(self.style.SUCCESS(t)))
        except db_migracion.ErrorMigracion as error:
            raise CommandError(str(error))
