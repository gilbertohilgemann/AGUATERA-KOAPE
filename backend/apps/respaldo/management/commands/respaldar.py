"""
Respaldo automático (lo corre la tarea programada: start respaldo-programar, o el timer del servidor).

Genera el backup completo, lo verifica, conserva los últimos RESPALDOS_A_CONSERVAR y, si
DIR_RESPALDOS_COPIA está configurada (disco externo, carpeta de red), deja allí una copia.
"""
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.auditoria.servicios import registrar
from apps.respaldo.restauracion import verificar
from apps.respaldo.servicios import generar_respaldo, limpiar_viejos


class Command(BaseCommand):
    help = 'Genera el respaldo automático, lo verifica y (si está configurado) lo copia a otra carpeta.'

    def handle(self, *args, **opciones):
        errores = []
        archivo = generar_respaldo()
        informe = verificar(archivo)
        if informe['errores']:
            errores.append(f'{archivo.name} no pasó la verificación: {" ".join(informe["errores"])}')
        destino_copia = settings.KOAPE.get('DIR_RESPALDOS_COPIA')
        if destino_copia:
            try:
                Path(destino_copia).mkdir(parents=True, exist_ok=True)
                shutil.copy2(archivo, Path(destino_copia) / archivo.name)
                limpiar_viejos(Path(destino_copia), settings.KOAPE['RESPALDOS_A_CONSERVAR'])
            except OSError as error:  # el disco externo puede no estar conectado: se avisa, no se corta
                errores.append(f'No se pudo copiar {archivo.name} a {destino_copia}: {error}')
        limpiar_viejos(archivo.parent, settings.KOAPE['RESPALDOS_A_CONSERVAR'])
        registrar('respaldo_automatico', usuario_nombre='sistema', entidad='respaldo', entidad_id=archivo.name,
                  errores=errores)
        self.stdout.write(self.style.SUCCESS(f'  ✓ {archivo.name}'))
        for error in errores:
            self.stderr.write(self.style.ERROR(f'  ✗ {error}'))
        if errores:
            raise CommandError('El respaldo automático terminó con errores.')
