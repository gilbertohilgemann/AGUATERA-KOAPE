"""Las dos aguateras de demostración de Itapúa (Encarnación y Cambyretá)."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.cobranzas.models import Pago, Recibo
from apps.facturacion.models import Factura
from apps.lecturas.models import Lectura
from apps.identidad.models import Usuario
from apps.padron.models import Cliente, Conexion, Medidor
from apps.plataforma.models import Institucion
from apps.territorio.models import Zona


class DemosItapuaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('cargar_demos_itapua', stdout=StringIO())

    def test_dos_aguateras_con_20_abonados_y_medidores(self):
        for codigo in ('DEMO-ENC', 'DEMO-CAM'):
            inst = Institucion.objects.get(codigo=codigo)
            self.assertEqual(Cliente.objects.de(inst).count(), 20)
            self.assertEqual(Conexion.objects.de(inst).count(), 20)
            self.assertEqual(Medidor.objects.de(inst).count(), 20)
            self.assertEqual(Zona.objects.de(inst).count(), 2)
            self.assertTrue(inst.portal_abonados)

    def test_historial_de_tres_meses_y_cobranzas(self):
        for codigo in ('DEMO-ENC', 'DEMO-CAM'):
            inst = Institucion.objects.get(codigo=codigo)
            self.assertEqual(Lectura.objects.filter(institucion=inst).count(), 60)
            self.assertEqual(Factura.objects.filter(institucion=inst).count(), 16)
            self.assertEqual(Pago.objects.filter(institucion=inst).count(), 14)   # 11 contado + 3 recibos
            self.assertEqual(Recibo.objects.filter(institucion=inst).count(), 3)

    def test_ubicadas_en_su_zona(self):
        enc = Conexion.objects.de(Institucion.objects.get(codigo='DEMO-ENC')).first()
        cam = Conexion.objects.de(Institucion.objects.get(codigo='DEMO-CAM')).first()
        self.assertAlmostEqual(float(enc.latitud), -27.33, delta=0.02)
        self.assertAlmostEqual(float(cam.longitud), -55.78, delta=0.02)

    def test_se_puede_repetir_sin_duplicar(self):
        salida = StringIO()
        call_command('cargar_demos_itapua', stdout=salida)
        self.assertIn('ya tiene datos', salida.getvalue())
        self.assertEqual(Cliente.objects.count(), 40)

    def test_los_tres_usuarios_entran_con_la_misma_contrasena(self):
        for codigo in ('DEMO-ENC', 'DEMO-CAM'):
            for nombre in ('admin', 'cobrador1', 'cajero1'):
                usuario = Usuario.objects.get(institucion__codigo=codigo, nombre_usuario=nombre)
                self.assertTrue(usuario.check_password('Acceso*2026'), f'{codigo}/{nombre}')
                self.assertFalse(usuario.debe_cambiar_contrasena)

    def test_repetir_restablece_la_contrasena(self):
        usuario = Usuario.objects.get(institucion__codigo='DEMO-ENC', nombre_usuario='cajero1')
        usuario.set_password('Otra.Clave.1')
        usuario.save()
        call_command('cargar_demos_itapua', stdout=StringIO())
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password('Acceso*2026'))
