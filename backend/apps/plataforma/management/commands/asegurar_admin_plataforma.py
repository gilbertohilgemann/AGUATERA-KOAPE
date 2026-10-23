"""
Crea o restablece el usuario administrador fijo de la PLATAFORMA.

Idempotente: correrlo de nuevo solo confirma el mismo usuario y su contraseña.
Usuario y contraseña salen de ADMIN_PLATAFORMA_USUARIO / ADMIN_PLATAFORMA_CONTRASENA (backend/.env).
"""
import os

from django.core.management.base import BaseCommand, CommandError

from apps.identidad.models import Usuario


class Command(BaseCommand):
    help = 'Crea o restablece el administrador fijo de la plataforma.'

    def handle(self, *args, **opciones):
        nombre = os.environ.get('ADMIN_PLATAFORMA_USUARIO', 'admin').strip().lower()
        contrasena = os.environ.get('ADMIN_PLATAFORMA_CONTRASENA', '').strip()
        correo = os.environ.get('ADMIN_PLATAFORMA_CORREO', '').strip()
        if not contrasena:
            raise CommandError('Falta ADMIN_PLATAFORMA_CONTRASENA en backend/.env')
        cuenta = Usuario.objects.filter(institucion__isnull=True, nombre_usuario=nombre).first()
        creado = cuenta is None
        if creado:
            cuenta = Usuario(nombre_usuario=nombre)
        cuenta.is_staff = True
        cuenta.is_superuser = True
        cuenta.is_active = True
        cuenta.intentos_fallidos = 0
        cuenta.bloqueado_hasta = None
        if correo:
            cuenta.correo = correo
        cuenta.set_password(contrasena)
        cuenta.save()
        self.stdout.write(self.style.SUCCESS(f'Administrador de plataforma "{nombre}" {"creado" if creado else "restablecido"}.'))
