"""
Copia de datos entre motores (dumpdata/loaddata hacia un alias temporal).

Se prueba SQLite → SQLite: el mecanismo es el mismo que hacia PostgreSQL. La prueba contra un
PostgreSQL real se hace en el servidor con el panel o `manage.py migrate_to_postgres`.
"""
import tempfile
from pathlib import Path

from django.db import connections
from django.test import TransactionTestCase

from apps.auditoria.models import RegistroAuditoria
from apps.identidad.models import Permiso, Rol, Usuario
from apps.migracion_bd import db_migracion
from apps.plataforma.models import Institucion
from comun.pruebas.utilidades import nueva_institucion


class CopiaEntreBasesTests(TransactionTestCase):
    def test_copia_todos_los_datos_con_relaciones(self):
        nueva_institucion('JUNTA-A')
        nueva_institucion('JUNTA-B')
        # El alias temporal no existe en settings: se habilita solo para esta prueba.
        CopiaEntreBasesTests.databases = frozenset({'default', 'destino_prueba'})
        with tempfile.TemporaryDirectory() as tmp:
            db_migracion.registrar_alias('destino_prueba', db_migracion.configuracion_sqlite(Path(tmp) / 'copia.sqlite3'))
            try:
                db_migracion.copiar_datos('default', 'destino_prueba')
                for modelo in (Institucion, Usuario, Rol, Permiso, RegistroAuditoria):
                    self.assertEqual(modelo.objects.using('destino_prueba').count(), modelo.objects.count(), modelo)
                rol = Rol.objects.using('destino_prueba').get(institucion__codigo='JUNTA-A', nombre='Consulta')
                self.assertEqual(sorted(rol.permisos.values_list('codigo', flat=True)), ['cobranzas.consultar', 'facturacion.consultar', 'institucion.ver', 'lecturas.consultar',
                                  'liquidaciones.consultar', 'mapa.ver', 'padron.consultar'])
                admin = Usuario.objects.using('destino_prueba').get(identificador='JUNTA-B/admin')
                self.assertTrue(admin.es_admin_institucion)
            finally:
                db_migracion.quitar_alias('destino_prueba')
                CopiaEntreBasesTests.databases = frozenset({'default'})
        self.assertNotIn('destino_prueba', connections.databases)

    def test_actualizar_env_conserva_el_resto(self):
        from django.test import override_settings
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / '.env'
            env.write_text('# comentario\nDEBUG=True\nDB_MOTOR=sqlite\n', encoding='utf-8')
            with override_settings(BASE_DIR=Path(tmp)):
                db_migracion.actualizar_env({'DB_MOTOR': 'postgres', 'DB_NOMBRE': 'koape_aguateras'})
            self.assertEqual(env.read_text(encoding='utf-8'),
                             '# comentario\nDEBUG=True\nDB_MOTOR=postgres\nDB_NOMBRE=koape_aguateras\n')
        import os
        os.environ.pop('DB_NOMBRE', None)
        os.environ['DB_MOTOR'] = 'sqlite'
