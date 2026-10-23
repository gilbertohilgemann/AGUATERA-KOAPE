import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.lecturas.models import Lectura
from apps.plataforma.models import Institucion
from apps.tarifas.models import Liquidacion
from comun.pruebas.utilidades import nueva_institucion


class DatosPruebaTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ajustes = override_settings(DIR_PRIVADO=Path(self.tmp))
        self.ajustes.enable()

    def tearDown(self):
        self.ajustes.disable()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_carga_un_escenario_completo_una_sola_vez(self):
        demo = nueva_institucion('DEMO')
        call_command('cargar_datos_prueba', stdout=StringIO())
        self.assertEqual(Lectura.objects.filter(institucion=demo, estado='confirmada').count(), 16)
        self.assertEqual(Liquidacion.objects.filter(institucion=demo, estado='vigente').count(), 16)
        self.assertEqual(Institucion.objects.get(pk=demo.pk).modalidad_facturacion, 'autoimpresa')
        # Segunda vez: no carga nada encima; solo completa lo que falte (datos de una versión anterior).
        from apps.padron.models import Cliente, Medidor
        Cliente.objects.filter(institucion=demo).update(correo='')
        Medidor.objects.filter(institucion=demo).update(numero='')
        Institucion.objects.filter(pk=demo.pk).update(portal_abonados=False)
        call_command('cargar_datos_prueba', stdout=StringIO())
        self.assertEqual(Lectura.objects.filter(institucion=demo, estado='confirmada').count(), 16)
        self.assertEqual(Cliente.objects.filter(institucion=demo).exclude(correo='').count(), 6)
        self.assertEqual(Medidor.objects.filter(institucion=demo).exclude(numero='').count(), 8)
        self.assertTrue(Institucion.objects.get(pk=demo.pk).portal_abonados)

    def test_no_carga_encima_de_un_padron_propio(self):
        from apps.padron import servicios as padron
        demo = nueva_institucion('DEMO')
        cliente = padron.crear_cliente(institucion=demo, datos={'Code': 'X1', 'nombre': 'Real'})
        padron.crear_conexion(institucion=demo, datos={'Code': 'X1', 'cliente': cliente})
        with self.assertRaises(CommandError):
            call_command('cargar_datos_prueba', stdout=StringIO())

    def test_solo_en_instituciones_de_demostracion(self):
        nueva_institucion('JUNTA-REAL')
        with self.assertRaises(CommandError):
            call_command('cargar_datos_prueba', 'JUNTA-REAL', stdout=StringIO())
