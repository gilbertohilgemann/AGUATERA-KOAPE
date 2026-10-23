"""
Convención SerNr: puntos de expedición, rangos de numeración y asignación del número de los documentos
de formulario continuo (facturas y notas de crédito).
"""
import datetime

from django.db import transaction
from django.test import TestCase

from apps.auditoria.models import RegistroAuditoria
from apps.facturacion.models import PuntoExpedicion, RangoNumeracion, formatear_sernr
from apps.facturacion.servicios import tomar_sernr
from comun.errores import ErrorNegocio
from comun.pruebas.utilidades import LimpiarLimites, admin_de, cliente_de, nueva_institucion, usuario_con_permisos


class BaseNumeracion(LimpiarLimites, TestCase):
    def setUp(self):
        super().setUp()
        self.a = nueva_institucion('JUNTA-A')
        self.b = nueva_institucion('JUNTA-B')
        admin_de(self.a)
        admin_de(self.b)
        self.api = cliente_de(self.a)
        self.api_b = cliente_de(self.b)

    def post(self, ruta, datos, codigo=201, api=None):
        r = (api or self.api).post(f'/api/v1/{ruta}', datos, format='json')
        self.assertEqual(r.status_code, codigo, r.data)
        return r.data

    def punto(self, code='CENTRAL', est='001', pto='001', api=None):
        return self.post('puntos-expedicion/', {'Code': code, 'establecimiento': est, 'punto': pto,
                                                'nombre': f'Punto {code}'}, api=api)

    def rango(self, code, punto, desde, hasta, tipo='factura', codigo=201, **extra):
        return self.post('rangos-numeracion/', {'Code': code, 'punto': punto, 'tipo_documento': tipo,
                                                'desde': desde, 'hasta': hasta, **extra}, codigo=codigo)

    def tomar(self, code_punto, tipo='factura', institucion=None, fecha=None):
        punto = PuntoExpedicion.objects.get(institucion=institucion or self.a, Code=code_punto)
        with transaction.atomic():
            return tomar_sernr(punto, tipo, institucion=institucion or self.a, fecha=fecha)


class PuntosYRangosTests(BaseNumeracion):
    def test_varios_puntos_cada_uno_con_su_numeracion(self):
        self.punto('CENTRAL', '001', '001')
        self.punto('MOVIL', '001', '002')
        self.rango('FAC-C', 'CENTRAL', 1, 3)
        self.rango('FAC-M', 'MOVIL', 1, 3)
        self.rango('NC-C', 'CENTRAL', 1, 3, tipo='nota_credito')
        self.assertEqual([self.tomar('CENTRAL')[0] for _ in range(2)], [1, 2])
        self.assertEqual(self.tomar('MOVIL')[0], 1)                     # otro punto, su propia serie
        self.assertEqual(self.tomar('CENTRAL', 'nota_credito')[0], 1)  # otro tipo, su propia serie
        punto = PuntoExpedicion.objects.get(institucion=self.a, Code='CENTRAL')
        self.assertEqual(formatear_sernr(punto, 123), '001-001-0000123')

    def test_al_agotarse_sigue_con_el_proximo_rango_y_sin_rangos_no_emite(self):
        self.punto()
        self.rango('R1', 'CENTRAL', 1, 2)
        self.rango('R2', 'CENTRAL', 101, 102)
        numeros = [self.tomar('CENTRAL') for _ in range(4)]
        self.assertEqual([n for n, _ in numeros], [1, 2, 101, 102])
        self.assertEqual([r.Code for _, r in numeros], ['R1', 'R1', 'R2', 'R2'])
        with self.assertRaises(ErrorNegocio) as error:
            self.tomar('CENTRAL')
        self.assertEqual(error.exception.codigo, 'sin_numeracion')
        datos = self.api.get('/api/v1/rangos-numeracion/R1/').data
        self.assertEqual((datos['en_uso'], datos['agotado']), (True, True))

    def test_vigencia_y_rango_inactivo(self):
        self.punto()
        self.rango('VIEJO', 'CENTRAL', 1, 100, timbrado='111', vigencia_hasta='2025-12-31')
        self.rango('NUEVO', 'CENTRAL', 1, 100, timbrado='222', vigencia_desde='2026-01-01')
        self.assertEqual(self.tomar('CENTRAL', fecha=datetime.date(2025, 6, 1))[1].Code, 'VIEJO')
        numero, rango = self.tomar('CENTRAL', fecha=datetime.date(2026, 6, 1))
        self.assertEqual((numero, rango.Code, rango.timbrado), (1, 'NUEVO', '222'))  # timbrado nuevo, vuelve a 1
        self.api.patch('/api/v1/rangos-numeracion/NUEVO/', {'activo': False}, format='json')
        with self.assertRaises(ErrorNegocio):
            self.tomar('CENTRAL', fecha=datetime.date(2026, 6, 1))

    def test_rangos_superpuestos_se_rechazan(self):
        self.punto()
        self.punto('OTRO', '002', '001')
        self.rango('R1', 'CENTRAL', 1, 100, timbrado='111', vigencia_hasta='2025-12-31')
        self.rango('R2', 'CENTRAL', 50, 150, timbrado='111', codigo=400)
        self.rango('R3', 'CENTRAL', 100, 200, timbrado='111', codigo=400)
        self.rango('R4', 'CENTRAL', 101, 200, timbrado='111', vigencia_hasta='2025-12-31')                  # contiguo: válido
        self.rango('R5', 'CENTRAL', 1, 100, timbrado='999', vigencia_desde='2026-01-01')  # otro timbrado, otra vigencia
        self.rango('R5B', 'CENTRAL', 1, 100, timbrado='888', codigo=400)         # otro timbrado en la misma fecha
        self.rango('R6', 'CENTRAL', 1, 100, tipo='nota_credito', timbrado='111')  # otro tipo: válido
        self.rango('R7', 'OTRO', 1, 100, timbrado='111')                         # otro punto: válido
        self.rango('R8', 'CENTRAL', 10, 5, codigo=400)                           # hasta < desde
        self.rango('R9', 'CENTRAL', 0, 5, codigo=400)
        self.rango('R1', 'CENTRAL', 500, 600, codigo=400)                        # Code repetido

    def test_rango_usado_solo_se_amplia(self):
        self.punto()
        self.rango('R1', 'CENTRAL', 1, 10)
        self.tomar('CENTRAL')
        self.tomar('CENTRAL')
        url = '/api/v1/rangos-numeracion/R1/'
        for cambio in ({'desde': 2}, {'tipo_documento': 'nota_credito'}, {'timbrado': 'X'}, {'hasta': 1}):
            self.assertEqual(self.api.patch(url, cambio, format='json').status_code, 400, cambio)
        self.assertEqual(self.api.patch(url, {'hasta': 50}, format='json').status_code, 200)
        r = self.api.patch('/api/v1/puntos-expedicion/CENTRAL/', {'punto': '009'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.api.patch('/api/v1/puntos-expedicion/CENTRAL/', {'nombre': 'Caja 1'},
                                        format='json').status_code, 200)
        self.assertEqual(self.api.delete(url).status_code, 405)
        self.assertTrue(RegistroAuditoria.objects.filter(accion='rango_numeracion_modificado', entidad_id='R1').exists())

    def test_si_el_documento_no_se_guarda_el_numero_no_se_consume(self):
        self.punto()
        self.rango('R1', 'CENTRAL', 1, 10)
        punto = PuntoExpedicion.objects.get(Code='CENTRAL')
        try:
            with transaction.atomic():
                tomar_sernr(punto, 'factura', institucion=self.a)
                raise ErrorNegocio('falla al guardar la factura')
        except ErrorNegocio:
            pass
        self.assertEqual(self.tomar('CENTRAL')[0], 1)


class NumeracionNoRetrocedeTests(BaseNumeracion):
    """Casos de la revisión independiente: el SerNr de un punto y tipo nunca vuelve atrás."""

    def test_rango_nuevo_por_debajo_de_lo_emitido_se_rechaza(self):
        self.punto()
        self.rango('ALTO', 'CENTRAL', 101, 200)
        self.assertEqual(self.tomar('CENTRAL')[0], 101)
        self.rango('BAJO', 'CENTRAL', 1, 100, codigo=400)
        self.rango('SIGUE', 'CENTRAL', 201, 300)
        self.assertEqual(self.tomar('CENTRAL')[0], 102)

    def test_ampliar_un_rango_agotado_detras_de_otro_en_uso_se_rechaza(self):
        self.punto()
        self.rango('R1', 'CENTRAL', 1, 2)
        self.rango('R2', 'CENTRAL', 101, 102)
        for _ in range(3):
            self.tomar('CENTRAL')
        r = self.api.patch('/api/v1/rangos-numeracion/R1/', {'hasta': 50}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.tomar('CENTRAL')[0], 102)

    def test_rango_sin_vigencia_va_primero_en_cualquier_motor(self):
        self.punto()
        self.rango('ABIERTO', 'CENTRAL', 1, 1, timbrado='1', vigencia_hasta='2026-12-31')
        self.rango('DESPUES', 'CENTRAL', 1, 10, timbrado='2', vigencia_desde='2027-01-01')
        self.assertEqual(self.tomar('CENTRAL', fecha=datetime.date(2026, 5, 1))[1].Code, 'ABIERTO')

    def test_no_se_mueve_un_rango_a_un_punto_desactivado(self):
        self.punto()
        self.punto('OTRO', '002', '001')
        self.api.patch('/api/v1/puntos-expedicion/OTRO/', {'activo': False}, format='json')
        self.rango('R1', 'CENTRAL', 1, 10)
        r = self.api.patch('/api/v1/rangos-numeracion/R1/', {'punto': 'OTRO'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_tomar_sernr_con_punto_de_otra_institucion(self):
        self.punto('SOLO-B', api=self.api_b)
        punto_b = PuntoExpedicion.objects.get(institucion=self.b, Code='SOLO-B')
        with self.assertRaises(ErrorNegocio), transaction.atomic():
            tomar_sernr(punto_b, 'factura', institucion=self.a)


class ContadorInternoTests(BaseNumeracion):
    def test_el_contador_interno_y_el_id_no_se_exponen(self):
        self.punto()
        self.rango('R1', 'CENTRAL', 1, 10)
        self.tomar('CENTRAL')
        for ruta in ('puntos-expedicion/', 'puntos-expedicion/CENTRAL/', 'rangos-numeracion/', 'rangos-numeracion/R1/'):
            texto = self.api.get(f'/api/v1/{ruta}').content.decode()
            self.assertNotIn('ultimo_usado', texto, ruta)
            self.assertNotIn('"id"', texto, ruta)
        # Aunque se lo mande, el contador no se puede fijar desde la API.
        self.api.patch('/api/v1/rangos-numeracion/R1/', {'ultimo_usado': 9, 'observaciones': 'x'}, format='json')
        self.assertEqual(RangoNumeracion.objects.get(Code='R1').ultimo_usado, 1)
        self.post('rangos-numeracion/', {'Code': 'R2', 'punto': 'CENTRAL', 'tipo_documento': 'nota_credito',
                                         'desde': 1, 'hasta': 5, 'ultimo_usado': 4})
        self.assertIsNone(RangoNumeracion.objects.get(Code='R2').ultimo_usado)


class AislamientoYPermisosTests(BaseNumeracion):
    def test_cada_institucion_con_sus_puntos(self):
        self.punto('CENTRAL')
        self.punto('SOLO-B', api=self.api_b)
        self.assertEqual(self.api.get('/api/v1/puntos-expedicion/SOLO-B/').status_code, 404)
        self.rango('R1', 'SOLO-B', 1, 10, codigo=400)   # punto de otra institución: «no existe»
        self.punto('CENTRAL', '002', '001', api=self.api_b)  # el mismo Code en otra institución: válido
        self.assertEqual(len(self.api.get('/api/v1/puntos-expedicion/').data), 1)

    def test_permisos(self):
        self.punto()
        usuario_con_permisos(self.a, 'consulta', ['institucion.ver'])
        consulta = cliente_de(self.a, 'consulta')
        self.assertEqual(consulta.get('/api/v1/puntos-expedicion/').status_code, 200)
        r = consulta.post('/api/v1/puntos-expedicion/', {'Code': 'X', 'establecimiento': '002', 'punto': '001',
                                                         'nombre': 'X'}, format='json')
        self.assertEqual(r.status_code, 403)
        usuario_con_permisos(self.a, 'nadie', ['padron.consultar'])
        self.assertEqual(cliente_de(self.a, 'nadie').get('/api/v1/puntos-expedicion/').status_code, 403)
