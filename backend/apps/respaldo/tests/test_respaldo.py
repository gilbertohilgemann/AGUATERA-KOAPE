"""Backup completo: contenido, exclusiones, verificación y restauración."""
import tempfile
import unittest
import zipfile
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings

from apps.plataforma.models import Institucion
from apps.respaldo.restauracion import restaurar, verificar
from apps.respaldo.servicios import generar_respaldo, limpiar_viejos
from comun.pruebas.utilidades import nueva_institucion


def _proyecto_falso(raiz: Path) -> None:
    """Árbol de proyecto con todo lo que el backup debe incluir y excluir."""
    for relativo in ('backend/manage.py', 'backend/.env', 'frontend/src/main.tsx', 'backend/media/logo.png',
                     'backend/privado/medidores/foto.jpg', '.git/config', '.github/workflows/ci.yml', '.gitignore',
                     'backend/venv/lib/x.py', 'frontend/node_modules/react/index.js', 'frontend/dist/index.html',
                     'backend/apps/__pycache__/x.pyc', 'backend/staticfiles/a.css', 'frontend/.vite/cache'):
        ruta = raiz / relativo
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text('x')


class RespaldoTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        raiz = Path(self.tmp.name) / 'proyecto'
        _proyecto_falso(raiz)
        self.ajustes = override_settings(RAIZ_PROYECTO=raiz, DIR_RESPALDOS=Path(self.tmp.name) / 'respaldos')
        self.ajustes.enable()
        nueva_institucion('JUNTA-SL')

    def tearDown(self):
        self.ajustes.disable()
        self.tmp.cleanup()

    @unittest.skipUnless(connection.vendor == 'sqlite', 'Prueba del respaldo con SQLite (con PostgreSQL se usa pg_dump; se prueba en el servidor).')
    def test_incluye_codigo_base_y_archivos_y_excluye_lo_regenerable_y_el_repositorio(self):
        archivo = generar_respaldo()
        nombres = set(zipfile.ZipFile(archivo).namelist())
        for incluido in ('codigo/backend/manage.py', 'codigo/backend/.env', 'codigo/frontend/src/main.tsx',
                         'codigo/backend/media/logo.png', 'codigo/backend/privado/medidores/foto.jpg',
                         'base/aguateras.sqlite3', 'manifiesto.json'):
            self.assertIn(incluido, nombres)
        prohibidos = ('.git/', '.github/', '.gitignore', 'venv/', 'node_modules/', 'dist/', '__pycache__', 'staticfiles/', '.vite/')
        for nombre in nombres:
            for prohibido in prohibidos:
                self.assertNotIn(prohibido, nombre)

    @unittest.skipUnless(connection.vendor == 'sqlite', 'Prueba del respaldo con SQLite (con PostgreSQL se usa pg_dump; se prueba en el servidor).')
    def test_verificar_y_limpiar_viejos(self):
        archivo = generar_respaldo()
        informe = verificar(archivo)
        self.assertEqual(informe['errores'], [])
        self.assertEqual(informe['base']['integridad'], 'ok')
        for _ in range(3):
            generar_respaldo()
        limpiar_viejos(archivo.parent, 2)
        self.assertEqual(len(list(archivo.parent.glob('*.zip'))), 2)

    def test_un_zip_ajeno_no_pasa_la_verificacion(self):
        ajeno = Path(self.tmp.name) / 'ajeno.zip'
        with zipfile.ZipFile(ajeno, 'w') as z:
            z.writestr('../../etc/passwd', 'x')
        self.assertTrue(verificar(ajeno)['errores'])


class RestauracionTests(TransactionTestCase):
    @unittest.skipUnless(connection.vendor == 'sqlite', 'Prueba del respaldo con SQLite (con PostgreSQL se usa pg_dump; se prueba en el servidor).')
    def test_restaurar_vuelve_los_datos_al_momento_del_respaldo(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp) / 'proyecto'
            _proyecto_falso(raiz)
            with override_settings(RAIZ_PROYECTO=raiz, DIR_RESPALDOS=Path(tmp) / 'respaldos',
                                   MEDIA_ROOT=raiz / 'backend' / 'media', DIR_PRIVADO=raiz / 'backend' / 'privado'):
                nueva_institucion('ANTES')
                archivo = generar_respaldo()
                nueva_institucion('DESPUES')
                (raiz / 'backend' / 'privado' / 'medidores' / 'foto.jpg').unlink()
                resultado = restaurar(archivo)
                self.assertEqual(set(Institucion.objects.values_list('codigo', flat=True)), {'ANTES'})
                self.assertTrue((raiz / 'backend' / 'privado' / 'medidores' / 'foto.jpg').exists())
                self.assertTrue(Path(resultado['respaldo_previo']).exists())
        self.assertTrue(Path(settings.DATABASES['default']['TEST']['NAME']).exists())
