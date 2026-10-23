"""Portal de abonados: activación con documento + correo del padrón, PIN por correo, contraseña y consulta propia
en todas las instituciones (y solo lo propio)."""
import re
from datetime import timedelta

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.caja.tests.test_caja import BaseCaja
from apps.padron import servicios as padron
from apps.padron.models import Cliente, TitularidadConexion
from apps.plataforma.models import Institucion
from apps.portal.models import CuentaAbonado
from comun.documentos import normalizar_documento
from comun.pruebas.utilidades import nueva_institucion

CLAVE = 'Mi.Clave.Segura.2026'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PortalTests(BaseCaja):
    def setUp(self):
        super().setUp()
        cache.clear()
        Institucion.objects.filter(pk=self.a.pk).update(portal_abonados=True)
        Cliente.objects.filter(institucion=self.a, Code='C1').update(documento='1.234.567', correo='maria@ejemplo.com')
        Cliente.objects.filter(institucion=self.a, Code='C1').first().save()   # recalcula el documento normalizado
        self.web = APIClient()

    def pin(self, documento='1234567', correo='maria@ejemplo.com'):
        r = self.web.post('/api/v1/portal/solicitar-pin/', {'documento': documento, 'correo': correo}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        return re.search(r'\b(\d{6})\b', mail.outbox[-1].body).group(1) if mail.outbox else None

    def ingresar(self, usuario, clave, codigo=200):
        r = self.web.post('/api/v1/portal/ingresar/', {'usuario': usuario, 'clave': clave}, format='json')
        self.assertEqual(r.status_code, codigo, r.data)
        return r.data

    def abonado(self, usuario='1234567'):
        pin = self.pin()
        token = self.ingresar(usuario, pin)['token']
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Portal {token}')
        self.assertEqual(api.post('/api/v1/portal/cambiar-clave/', {'nueva': CLAVE}, format='json').status_code, 200)
        return api

    def test_normalizacion_de_documentos(self):
        self.assertEqual({normalizar_documento(x) for x in ('1.234.567', '1234567', '1234567-8', ' 1 234 567 ')},
                         {'1234567'})

    def test_activacion_solo_con_el_correo_del_padron(self):
        # Correo distinto al del padrón: misma respuesta, pero no se envía nada ni se crea la cuenta.
        r = self.web.post('/api/v1/portal/solicitar-pin/', {'documento': '1234567', 'correo': 'otro@ejemplo.com'},
                          format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual((len(mail.outbox), CuentaAbonado.objects.count()), (0, 0))
        # Institución sin portal: tampoco.
        Institucion.objects.filter(pk=self.a.pk).update(portal_abonados=False)
        self.pin()
        self.assertEqual(len(mail.outbox), 0)
        Institucion.objects.filter(pk=self.a.pk).update(portal_abonados=True)
        pin = self.pin(documento='1.234.567-8', correo='MARIA@ejemplo.com')     # RUC con DV y mayúsculas
        self.assertEqual(len(pin), 6)
        self.assertNotIn(pin, CuentaAbonado.objects.get().pin)                  # solo el hash

    def test_pin_una_vez_luego_clave_propia(self):
        pin = self.pin()
        datos = self.ingresar('maria@ejemplo.com', pin)
        self.assertTrue(datos['debe_cambiar_clave'])
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Portal {datos["token"]}')
        self.assertEqual(api.get('/api/v1/portal/resumen/').status_code, 403)    # primero la contraseña
        self.assertEqual(api.post('/api/v1/portal/cambiar-clave/', {'nueva': '123'}, format='json').status_code, 400)
        self.assertEqual(api.post('/api/v1/portal/cambiar-clave/', {'nueva': CLAVE}, format='json').status_code, 200)
        self.ingresar('1234567', pin, codigo=400)                                # el PIN ya se usó
        self.ingresar('1234567', CLAVE)
        self.assertEqual(api.get('/api/v1/portal/resumen/').status_code, 200)

    def test_bloqueo_por_intentos(self):
        self.abonado()
        for _ in range(5):
            self.ingresar('1234567', 'mal', codigo=400)
        # Bloqueada: ni la contraseña correcta entra, y la respuesta es la misma que con un dato incorrecto
        # (no revela qué documentos tienen cuenta).
        bloqueada = self.ingresar('1234567', CLAVE, codigo=400)
        inexistente = self.ingresar('7654321', CLAVE, codigo=400)
        self.assertEqual((bloqueada['codigo'], bloqueada['detalle']), (inexistente['codigo'], inexistente['detalle']))

    def test_pedidos_repetidos_y_documentos_de_relleno_responden_igual(self):
        self.pin()
        r = self.web.post('/api/v1/portal/solicitar-pin/', {'documento': '1234567', 'correo': 'maria@ejemplo.com'},
                          format='json')
        self.assertEqual((r.status_code, len(mail.outbox)), (200, 1))         # no reenvía ni avisa que coincidió
        padron.crear_cliente(institucion=self.a, datos={'Code': 'C8', 'nombre': 'Sin documento', 'documento': '0',
                                                         'correo': 'x@ejemplo.com'})
        self.pin(documento='0', correo='x@ejemplo.com')
        self.assertEqual((len(mail.outbox), CuentaAbonado.objects.filter(documento='0').exists()), (1, False))

    def test_ve_su_cuenta_en_todas_las_instituciones_y_solo_lo_propio(self):
        f = self.credito([self.oct])
        self.cobrar(10000, [(f, 10000)])
        b = nueva_institucion('JUNTA-B', 'Aguatera B')
        Institucion.objects.filter(pk=b.pk).update(portal_abonados=True)
        padron.crear_cliente(institucion=b, datos={'Code': 'B-1', 'nombre': 'María B.', 'documento': '1234567-8',
                                                    'correo': 'MARIA@ejemplo.com'})
        # Mismo documento pero OTRO correo (otra persona mal cargada, o un dato repetido): no se muestra.
        c = nueva_institucion('JUNTA-D', 'Aguatera D')
        Institucion.objects.filter(pk=c.pk).update(portal_abonados=True)
        padron.crear_cliente(institucion=c, datos={'Code': 'D-1', 'nombre': 'Otra', 'documento': '1234567',
                                                    'correo': 'otra@ejemplo.com'})
        padron.crear_cliente(institucion=self.a, datos={'Code': 'C9', 'nombre': 'Otro vecino', 'documento': '999'})
        api = self.abonado()
        resumen = {x['institucion']['codigo']: x for x in api.get('/api/v1/portal/resumen/').data}
        self.assertEqual(set(resumen), {'JUNTA-A', 'JUNTA-B'})
        self.assertEqual(resumen['JUNTA-A']['saldo_facturas'], '34800.00')
        deuda = api.get('/api/v1/portal/JUNTA-A/deuda/').data
        self.assertEqual([x['numero'] for x in deuda['facturas']], [f['numero']])
        self.assertEqual(len(deuda['pendientes_de_facturar']), 2)                # nov y la otra conexión
        self.assertEqual(len(api.get('/api/v1/portal/JUNTA-A/conexiones/').data), 2)
        self.assertEqual(len(api.get('/api/v1/portal/JUNTA-A/pagos/').data), 1)
        lecturas = api.get('/api/v1/portal/JUNTA-A/lecturas/').data
        self.assertEqual(len(lecturas), 3)
        pdf = api.get(f'/api/v1/portal/JUNTA-A/facturas/{f["referencia"]}/pdf/')
        self.assertEqual((pdf.status_code, pdf.content[:5]), (200, b'%PDF-'))
        recibo = api.get('/api/v1/portal/JUNTA-A/pagos/').data[0]['recibo']
        self.assertEqual(api.get(f'/api/v1/portal/JUNTA-A/recibos/{int(recibo)}/pdf/').status_code, 200)
        self.assertEqual(api.get(f'/api/v1/portal/JUNTA-A/lecturas/{lecturas[0]["comprobante"]}/foto/').status_code, 200)
        self.assertEqual(api.get('/api/v1/portal/JUNTA-D/deuda/').status_code, 404)
        # Lo de antes de ser titular no se ve: ni lecturas, ni consumos sin facturar, ni la última lectura.
        TitularidadConexion.objects.filter(conexion__institucion=self.a, cliente__Code='C1') \
            .update(desde=timezone.localdate() + timedelta(days=1))
        self.assertEqual(api.get('/api/v1/portal/JUNTA-A/lecturas/').data, [])
        self.assertEqual(api.get('/api/v1/portal/JUNTA-A/deuda/').data['pendientes_de_facturar'], [])
        self.assertEqual({c['ultima_lectura'] for c in api.get('/api/v1/portal/JUNTA-A/conexiones/').data}, {None})
        TitularidadConexion.objects.filter(conexion__institucion=self.a, cliente__Code='C1').update(desde='2026-01-01')
        # Lo ajeno no se ve: otra institución donde no es cliente, factura de otro cliente, la API del personal.
        nueva_institucion('JUNTA-C')
        self.assertEqual(api.get('/api/v1/portal/JUNTA-C/deuda/').status_code, 404)
        otra = self.emitir([self.nov], 'credito')
        Cliente.objects.filter(institucion=self.a, Code='C1').update(documento_normalizado='0')
        self.assertEqual(api.get(f'/api/v1/portal/JUNTA-A/facturas/{otra["referencia"]}/pdf/').status_code, 404)
        self.assertEqual(api.get('/api/v1/clientes/').status_code, 401)           # su sesión no sirve en el panel

    def test_salir_y_cambio_de_clave_cierra_otras_sesiones(self):
        api = self.abonado()
        token2 = self.ingresar('1234567', CLAVE)['token']
        otra = APIClient()
        otra.credentials(HTTP_AUTHORIZATION=f'Portal {token2}')
        self.assertEqual(otra.post('/api/v1/portal/cambiar-clave/', {'actual': CLAVE, 'nueva': CLAVE + 'x'},
                                   format='json').status_code, 200)
        self.assertEqual(api.get('/api/v1/portal/yo/').status_code, 401)
        self.assertEqual(otra.post('/api/v1/portal/salir/').status_code, 200)
        self.assertEqual(otra.get('/api/v1/portal/yo/').status_code, 401)
