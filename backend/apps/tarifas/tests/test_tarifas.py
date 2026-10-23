"""
Pruebas de la Fase 4: tarifas y liquidaciones.

Casos obligatorios de la sección 21: 6 (el consumo y el importe los calcula el servidor), 7 (una tarifa nueva no
altera liquidaciones históricas) y 8 (una lectura no se liquida dos veces; la factura llega en la Fase 5).
Criterio de aceptación: liquidaciones reproducibles que conservan los valores históricos.

Ejemplo de la tarifa usada (configuración confirmada por Koape Sistemas):
  consumo mínimo 10 m³ a Gs. 2.500 (se cobra se use o no), excedente Gs. 3.000 por m³, tasa ERSSAN 2 % exenta,
  lo demás gravado con IVA 10 % (calculado aparte).
  Consumo 15 m³ → mínimo 25.000 + excedente 15.000 = 40.000; ERSSAN 800; IVA 4.000; total 44.800.
"""
import shutil
import tempfile
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.auditoria.models import RegistroAuditoria
from apps.lecturas.models import Lectura
from apps.padron import servicios as padron
from apps.recorridos import servicios as recorridos
from apps.tarifas.calculo import ErrorTarifa, calcular
from apps.tarifas.models import Liquidacion
from comun.pruebas.utilidades import LimpiarLimites, admin_de, cliente_de, nueva_institucion, usuario_con_permisos

JPG = b'\xff\xd8\xff\xe0' + b'\x00' * 200
D = Decimal

MINIMO_EXCEDENTE_ERSSAN = [
    {'orden': 1, 'nombre': 'Consumo mínimo (10 m³)', 'tipo': 'minimo', 'cantidad': '10', 'precio': '2500', 'iva': '10'},
    {'orden': 2, 'nombre': 'Excedente', 'tipo': 'excedente', 'precio': '3000', 'iva': '10'},
    {'orden': 3, 'nombre': 'Tasa ERSSAN', 'tipo': 'porcentaje', 'porcentaje': '2', 'iva': 'exento'},
]


class CalculoTests(SimpleTestCase):
    """El motor es una función pura: mismos datos, mismo resultado."""

    def test_ejemplo_minimo_excedente_y_erssan(self):
        r = calcular(MINIMO_EXCEDENTE_ERSSAN, '15')
        self.assertEqual([(l['concepto'], l['cantidad'], l['importe']) for l in r['lineas']], [
            ('Consumo mínimo (10 m³)', D('10'), D('25000')), ('Excedente', D('5'), D('15000')),
            ('Tasa ERSSAN', D('40000'), D('800'))])
        self.assertEqual((r['subtotal_iva10'], r['subtotal_exento'], r['iva10'], r['total']),
                         (D('40000'), D('800'), D('4000'), D('44800')))

    def test_el_minimo_se_cobra_aunque_no_se_consuma(self):
        r = calcular(MINIMO_EXCEDENTE_ERSSAN, '0')
        self.assertEqual((r['lineas'][1]['importe'], r['total']), (D('0'), D('25000') + D('500') + D('2500')))

    def test_tramos_escalonados_fijo_e_iva5(self):
        conceptos = [
            {'nombre': 'Cargo fijo', 'tipo': 'fijo', 'precio': '5000', 'iva': '10'},
            {'nombre': '0 a 15 m³', 'tipo': 'tramo', 'desde': '0', 'hasta': '15', 'precio': '1000', 'iva': '5'},
            {'nombre': '16 a 40 m³', 'tipo': 'tramo', 'desde': '15', 'hasta': '40', 'precio': '2000', 'iva': '5'},
            {'nombre': 'Más de 40 m³', 'tipo': 'tramo', 'desde': '40', 'precio': '3000', 'iva': '5'},
        ]
        r = calcular(conceptos, '45.5')
        self.assertEqual([l['importe'] for l in r['lineas']], [D('5000'), D('15000'), D('50000'), D('16500')])
        self.assertEqual((r['subtotal_iva5'], r['iva5'], r['iva10'], r['total']),
                         (D('81500'), D('4075'), D('500'), D('5000') + D('81500') + D('4075') + D('500')))

    def test_redondeo_a_guaranies(self):
        r = calcular([{'nombre': 'm³', 'tipo': 'por_m3', 'precio': '1234', 'iva': '10'},
                      {'nombre': 'ERSSAN', 'tipo': 'porcentaje', 'porcentaje': '2', 'iva': 'exento'}], '2.345')
        # 2,345 × 1.234 = 2.893,73 → 2.894; ERSSAN 2 % de 2.894 = 57,88 → 58; IVA 289,4 → 289
        self.assertEqual([l['importe'] for l in r['lineas']], [D('2894'), D('58')])
        self.assertEqual((r['iva10'], r['total']), (D('289'), D('3241')))

    def test_configuraciones_invalidas(self):
        casos = [
            [{'nombre': 'x', 'tipo': 'excedente', 'precio': '1', 'iva': '10'}],                     # excedente sin mínimo
            [{'nombre': 'a', 'tipo': 'minimo', 'cantidad': '5', 'precio': '1', 'iva': '10'}] * 2,     # dos mínimos
            [{'nombre': 'a', 'tipo': 'tramo', 'desde': '0', 'hasta': '20', 'precio': '1', 'iva': '10'},
             {'nombre': 'b', 'tipo': 'tramo', 'desde': '10', 'precio': '1', 'iva': '10'}],            # tramos superpuestos
            [{'nombre': 'p', 'tipo': 'porcentaje', 'porcentaje': '0', 'iva': 'exento'}],
            [{'nombre': 'f', 'tipo': 'fijo', 'precio': '-1', 'iva': '10'}],
            [{'nombre': 'f', 'tipo': 'fijo', 'precio': '1', 'iva': '21'}],
            [{'nombre': '', 'tipo': 'fijo', 'precio': '1', 'iva': '10'}],
        ]
        for conceptos in casos:
            with self.assertRaises(ErrorTarifa, msg=str(conceptos)):
                calcular(conceptos, '10')


class BaseLiquidaciones(LimpiarLimites, TestCase):
    def setUp(self):
        super().setUp()
        self._privado = tempfile.mkdtemp()
        self._ajustes = override_settings(DIR_PRIVADO=Path(self._privado))
        self._ajustes.enable()
        self.a = nueva_institucion('JUNTA-A')
        admin_de(self.a)
        self.api = cliente_de(self.a)
        cliente = padron.crear_cliente(institucion=self.a, datos={'Code': 'C1', 'nombre': 'María'})
        self.conexiones = []
        for n in (1, 2):
            conexion = padron.crear_conexion(institucion=self.a, datos={
                'Code': f'CX{n}', 'cliente': cliente, 'latitud': D('-25.25'), 'longitud': D('-57.55')})
            medidor = padron.crear_medidor(institucion=self.a, datos={'Code': f'M{n}'})
            padron.instalar_medidor(conexion, medidor, fecha=date(2026, 1, 1), lectura_inicial=D('100'))
            self.conexiones.append(conexion)
        self.cobrador = usuario_con_permisos(self.a, 'cob', ['lecturas.registrar'])
        self.cob = cliente_de(self.a, 'cob')

    def tearDown(self):
        self._ajustes.disable()
        shutil.rmtree(self._privado, ignore_errors=True)
        super().tearDown()

    def tarifa(self, code='RES', nombre='Residencial', vigente_desde='2026-01', conceptos=MINIMO_EXCEDENTE_ERSSAN):
        r = self.api.post('/api/v1/tarifas/', {'Code': code, 'nombre': nombre}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        r = self.api.post(f'/api/v1/tarifas/{code}/versiones/', {'vigente_desde': vigente_desde, 'conceptos': conceptos},
                          format='json')
        self.assertEqual(r.status_code, 201, r.data)
        return r.data

    def recorrido(self, code, periodo):
        r = recorridos.crear_recorrido(institucion=self.a, datos={'Code': code, 'nombre': code, 'periodo': periodo})
        recorridos.agregar_conexiones(r, conexiones=self.conexiones)
        recorridos.asignar_cobrador(r, self.cobrador)
        recorridos.cambiar_estado(r, 'abierto')
        return r

    def leer(self, recorrido, medidor, lectura):
        r = self.cob.post('/api/v1/cobrador/lecturas/', {
            'id_operacion': str(uuid.uuid4()), 'recorrido': recorrido, 'medidor': medidor, 'lectura_actual': lectura,
            'capturada_en': timezone.now().isoformat(), 'latitud': '-25.25', 'longitud': '-57.55',
            'foto': SimpleUploadedFile('m.jpg', JPG)}, format='multipart')
        self.assertIn(r.status_code, (200, 201), r.data)
        return r.data

    def liquidacion_de(self, comprobante):
        return Liquidacion.objects.get(lectura__comprobante=comprobante, estado='vigente')


class LiquidacionTests(BaseLiquidaciones):
    def test_se_liquida_al_confirmarse_la_lectura(self):
        self.tarifa()
        self.recorrido('R10', '2026-10')
        lectura = self.leer('R10', 'M1', '115')  # consumo 15
        q = self.liquidacion_de(lectura['comprobante'])
        self.assertEqual((q.consumo, q.subtotal_iva10, q.subtotal_exento, q.iva10, q.total),
                         (D('15'), D('40000'), D('800'), D('4000'), D('44800')))
        self.assertEqual(q.tarifa.Code, 'RES')
        self.assertEqual(q.lineas.count(), 3)
        self.assertTrue(RegistroAuditoria.objects.filter(accion='liquidacion_generada', entidad_id=q.numero).exists())
        r = self.api.get(f'/api/v1/liquidaciones/{q.numero}/')
        self.assertEqual((r.status_code, r.data['lectura'], D(r.data['total'])), (200, lectura['comprobante'], D('44800')))
        self.assertNotIn('id', r.data)

    def test_la_liquidacion_es_reproducible_desde_su_instantanea(self):
        self.tarifa()
        self.recorrido('R10', '2026-10')
        q = self.liquidacion_de(self.leer('R10', 'M1', '137.25')['comprobante'])
        r = calcular(q.parametros, q.consumo)
        self.assertEqual(r['total'], q.total)
        self.assertEqual([(l['concepto'], l['importe']) for l in r['lineas']],
                         [(l.concepto, l.importe) for l in q.lineas.all()])

    def test_una_tarifa_nueva_no_altera_las_liquidaciones_historicas(self):
        self.tarifa()
        self.recorrido('R10', '2026-10')
        octubre = self.liquidacion_de(self.leer('R10', 'M1', '115')['comprobante'])
        # Una versión usada no se modifica…
        r = self.api.patch('/api/v1/tarifas/RES/versiones/2026-01/', {'conceptos': [
            {'nombre': 'Todo', 'tipo': 'fijo', 'precio': '1', 'iva': '10'}]}, format='json')
        self.assertEqual(r.status_code, 400)
        # …se crea otra, vigente desde noviembre, con precios nuevos.
        nuevos = [dict(c) for c in MINIMO_EXCEDENTE_ERSSAN]
        nuevos[0] = {**nuevos[0], 'precio': '3000'}
        r = self.api.post('/api/v1/tarifas/RES/versiones/', {'vigente_desde': '2026-11', 'conceptos': nuevos}, format='json')
        self.assertEqual(r.status_code, 201)
        self.recorrido('R11', '2026-11')
        noviembre = self.liquidacion_de(self.leer('R11', 'M1', '130')['comprobante'])  # consumo 15 de nuevo
        octubre.refresh_from_db()
        self.assertEqual((octubre.total, octubre.version.vigente_desde), (D('44800'), '2026-01'))
        self.assertEqual((noviembre.version.vigente_desde, noviembre.subtotal_iva10), ('2026-11', D('45000')))

    def test_no_se_liquida_dos_veces(self):
        from apps.tarifas.servicios import liquidar
        from comun.errores import ErrorNegocio
        self.tarifa()
        self.recorrido('R10', '2026-10')
        lectura = Lectura.objects.get(comprobante=self.leer('R10', 'M1', '115')['comprobante'])
        with self.assertRaises(ErrorNegocio), transaction.atomic():
            liquidar(lectura)
        q = Liquidacion.objects.get(lectura=lectura)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Liquidacion.objects.create(**{f.name: getattr(q, f.name) for f in Liquidacion._meta.fields
                                          if f.name not in ('id', 'numero', 'creado_en', 'actualizado_en')}, numero='LQ-OTRA')

    def test_lectura_en_revision_no_se_liquida_hasta_autorizarla(self):
        self.tarifa()
        self.recorrido('R10', '2026-10')
        lectura = self.leer('R10', 'M1', '50')  # menor que la anterior → revisión
        self.assertFalse(Liquidacion.objects.exists())
        self.api.post(f'/api/v1/lecturas/{lectura["comprobante"]}/autorizar/', {'motivo': 'vuelta a cero', 'consumo': '12'},
                      format='json')
        # consumo 12: mínimo 25.000 + excedente 6.000 = 31.000; ERSSAN 620; IVA 3.100
        self.assertEqual(self.liquidacion_de(lectura['comprobante']).total, D('34720'))

    def test_corregir_o_anular_la_lectura_anula_la_liquidacion_y_reliquida(self):
        self.tarifa()
        self.recorrido('R10', '2026-10')
        lectura = self.leer('R10', 'M1', '115')
        url = f'/api/v1/lecturas/{lectura["comprobante"]}'
        primera = self.liquidacion_de(lectura['comprobante'])
        self.api.post(f'{url}/corregir/', {'lectura_actual': '120', 'motivo': 'Se ve 120'}, format='json')
        primera.refresh_from_db()
        segunda = self.liquidacion_de(lectura['comprobante'])
        self.assertEqual((primera.estado, segunda.consumo, segunda.total),
                         ('anulada', D('20'), D('25000') + D('30000') + D('1100') + D('5500')))
        self.api.post(f'{url}/anular/', {'motivo': 'Lectura de prueba'}, format='json')
        self.assertFalse(Liquidacion.objects.filter(estado='vigente').exists())
        self.assertEqual(Liquidacion.objects.count(), 2)  # nada se borra

    def test_sin_tarifa_queda_sin_liquidar_y_despues_se_liquida(self):
        self.recorrido('R10', '2026-10')
        lectura = self.leer('R10', 'M1', '115')
        self.assertEqual(lectura['estado'], 'confirmada')
        self.assertEqual(self.api.get('/api/v1/liquidaciones-resumen/?periodo=2026-10').data['sin_liquidar'], 1)
        self.tarifa(vigente_desde='2026-11')  # todavía no vigente en octubre
        r = self.api.post('/api/v1/liquidaciones/liquidar-pendientes/', {'periodo': '2026-10'}, format='json')
        self.assertEqual(r.data, {'liquidadas': [], 'sin_tarifa': [lectura['comprobante']]})
        self.api.post('/api/v1/tarifas/RES/versiones/', {'vigente_desde': '2026-01', 'conceptos': MINIMO_EXCEDENTE_ERSSAN},
                      format='json')
        r = self.api.post('/api/v1/liquidaciones/liquidar-pendientes/', {'periodo': '2026-10'}, format='json')
        self.assertEqual(r.data['liquidadas'], [lectura['comprobante']])
        resumen = self.api.get('/api/v1/liquidaciones-resumen/?periodo=2026-10').data
        self.assertEqual((resumen['sin_liquidar'], D(resumen['total'])), (0, D('44800')))


class TarifasTests(BaseLiquidaciones):
    def test_tarifa_por_tipo_de_conexion_y_por_defecto(self):
        self.tarifa()  # la primera queda por defecto
        self.tarifa('COM', 'Comercial', conceptos=[{'nombre': 'm³', 'tipo': 'por_m3', 'precio': '5000', 'iva': '10'}])
        r = self.api.patch('/api/v1/conexiones/CX2/', {'tarifa': 'com'}, format='json')
        self.assertEqual((r.status_code, r.data['tarifa'], r.data['tarifa_nombre']), (200, 'COM', 'Comercial'))
        self.recorrido('R10', '2026-10')
        residencial = self.liquidacion_de(self.leer('R10', 'M1', '115')['comprobante'])
        comercial = self.liquidacion_de(self.leer('R10', 'M2', '115')['comprobante'])
        self.assertEqual((residencial.tarifa.Code, comercial.tarifa.Code, comercial.total),
                         ('RES', 'COM', D('75000') + D('7500')))
        # Cambiar la tarifa por defecto deja una sola marcada.
        self.api.patch('/api/v1/tarifas/COM/', {'por_defecto': True}, format='json')
        datos = {t['Code']: t['por_defecto'] for t in self.api.get('/api/v1/tarifas/').data}
        self.assertEqual(datos, {'COM': True, 'RES': False})
        self.assertEqual(self.api.patch('/api/v1/tarifas/COM/', {'activa': False}, format='json').status_code, 400)

    def test_simulador_y_validaciones(self):
        self.tarifa()
        r = self.api.post('/api/v1/tarifas/RES/simular/', {'periodo': '2026-10', 'consumo': '15'}, format='json')
        self.assertEqual((r.status_code, D(r.data['total'])), (200, D('44800')))
        r = self.api.post('/api/v1/tarifas/RES/simular/', {'periodo': '2025-12', 'consumo': '15'}, format='json')
        self.assertEqual(r.status_code, 400)  # sin versión vigente
        r = self.api.post('/api/v1/tarifas/RES/versiones/', {'vigente_desde': '2026-05', 'conceptos': [
            {'nombre': 'Excedente', 'tipo': 'excedente', 'precio': '1', 'iva': '10'}]}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.api.post('/api/v1/tarifas/RES/versiones/', {'vigente_desde': '2026-01', 'conceptos': MINIMO_EXCEDENTE_ERSSAN},
                          format='json')
        self.assertEqual(r.status_code, 400)  # ya existe esa vigencia
        # Una versión sin usar sí se corrige.
        r = self.api.patch('/api/v1/tarifas/RES/versiones/2026-01/', {'conceptos': MINIMO_EXCEDENTE_ERSSAN[:1]}, format='json')
        self.assertEqual((r.status_code, len(r.data['versiones'][0]['conceptos'])), (200, 1))

    def test_permisos_y_aislamiento(self):
        self.tarifa()
        usuario_con_permisos(self.a, 'consulta', ['liquidaciones.consultar'])
        consulta = cliente_de(self.a, 'consulta')
        self.assertEqual(consulta.get('/api/v1/tarifas/').status_code, 200)
        self.assertEqual(consulta.post('/api/v1/tarifas/', {'Code': 'X', 'nombre': 'X'}, format='json').status_code, 403)
        self.assertEqual(self.cob.get('/api/v1/liquidaciones/').status_code, 403)
        b = nueva_institucion('JUNTA-B')
        admin_de(b)
        otra = cliente_de(b)
        self.assertEqual(otra.get('/api/v1/tarifas/RES/').status_code, 404)
        self.assertEqual(otra.get('/api/v1/tarifas/').data, [])
        r = self.api.patch('/api/v1/conexiones/CX1/', {'tarifa': 'NO-EXISTE'}, format='json')
        self.assertEqual(r.status_code, 400)


class CasosDeLaRevisionTests(BaseLiquidaciones):
    """Casos que encontró la revisión independiente de la Fase 4."""

    def test_una_version_no_puede_alcanzar_periodos_ya_liquidados(self):
        self.tarifa()
        self.recorrido('R10', '2026-10')
        self.leer('R10', 'M1', '115')
        for periodo in ('2026-03', '2026-10'):
            r = self.api.post('/api/v1/tarifas/RES/versiones/', {'vigente_desde': periodo, 'conceptos': MINIMO_EXCEDENTE_ERSSAN},
                              format='json')
            self.assertEqual(r.status_code, 400, periodo)
        r = self.api.post('/api/v1/tarifas/RES/versiones/', {'vigente_desde': '2026-11', 'conceptos': MINIMO_EXCEDENTE_ERSSAN},
                          format='json')
        self.assertEqual(r.status_code, 201)

    def test_combinaciones_que_cobrarian_dos_veces_o_dejarian_m3_sin_precio(self):
        malos = [
            MINIMO_EXCEDENTE_ERSSAN + [{'nombre': 't', 'tipo': 'tramo', 'desde': '10', 'precio': '1', 'iva': '10'}],
            [{'nombre': 'm', 'tipo': 'minimo', 'cantidad': '10', 'precio': '1', 'iva': '10'},
             {'nombre': 'p', 'tipo': 'por_m3', 'precio': '1', 'iva': '10'}],
            [{'nombre': 'a', 'tipo': 'tramo', 'desde': '5', 'hasta': '10', 'precio': '1', 'iva': '10'},
             {'nombre': 'b', 'tipo': 'tramo', 'desde': '20', 'precio': '1', 'iva': '10'}],
            [{'nombre': 'a', 'tipo': 'tramo', 'desde': '0', 'hasta': '10', 'precio': '1', 'iva': '10'}],  # último con tope
            [{'nombre': 'p', 'tipo': 'por_m3', 'precio': '1', 'iva': '10'}] * 2,
        ]
        for conceptos in malos:
            with self.assertRaises(ErrorTarifa, msg=str(conceptos)):
                calcular(conceptos, '30')
        # Mínimo + tramos que empiezan donde termina el mínimo: válido.
        r = calcular([{'nombre': 'm', 'tipo': 'minimo', 'cantidad': '10', 'precio': '100', 'iva': '10'},
                      {'nombre': 't1', 'tipo': 'tramo', 'desde': '10', 'hasta': '20', 'precio': '200', 'iva': '10'},
                      {'nombre': 't2', 'tipo': 'tramo', 'desde': '20', 'precio': '300', 'iva': '10'}], '25')
        self.assertEqual([l['importe'] for l in r['lineas']], [D('1000'), D('2000'), D('1500')])

    def test_lectura_desmesurada_no_rompe(self):
        # Antes: la base de la tasa (en guaraníes) no entraba en la columna y daba error 500 en PostgreSQL.
        self.tarifa()
        self.recorrido('R10', '2026-10')
        lectura = self.leer('R10', 'M1', '99999999.999')
        q = self.liquidacion_de(lectura['comprobante'])
        self.assertEqual(q.total, calcular(q.parametros, q.consumo)['total'])
        self.assertGreater(q.lineas.get(tipo='porcentaje').cantidad, D('10') ** 11)

    def test_la_correccion_se_reliquida_con_la_tarifa_del_periodo(self):
        self.tarifa()
        self.tarifa('COM', 'Comercial', conceptos=[{'nombre': 'm³', 'tipo': 'por_m3', 'precio': '5000', 'iva': '10'}])
        self.recorrido('R10', '2026-10')
        lectura = self.leer('R10', 'M1', '115')
        self.api.patch('/api/v1/conexiones/CX1/', {'tarifa': 'COM'}, format='json')  # cambia después
        self.api.post(f'/api/v1/lecturas/{lectura["comprobante"]}/corregir/', {'lectura_actual': '116', 'motivo': 'x'},
                      format='json')
        self.assertEqual(self.liquidacion_de(lectura['comprobante']).tarifa.Code, 'RES')

    def test_permisos_de_lectura_simular_y_resumen(self):
        self.tarifa()
        usuario_con_permisos(self.a, 'consulta', ['liquidaciones.consultar'])
        r = cliente_de(self.a, 'consulta').post('/api/v1/tarifas/RES/simular/', {'periodo': '2026-10', 'consumo': '15'},
                                                  format='json')
        self.assertEqual((r.status_code, D(r.data['total'])), (200, D('44800')))
        usuario_con_permisos(self.a, 'tarifero', ['tarifas.gestionar'])
        self.assertEqual(cliente_de(self.a, 'tarifero').get('/api/v1/liquidaciones-resumen/').status_code, 200)
        usuario_con_permisos(self.a, 'padron', ['padron.consultar'])
        self.assertEqual(cliente_de(self.a, 'padron').get('/api/v1/tarifas/').status_code, 200)

    def test_la_tarifa_por_defecto_no_nace_inactiva(self):
        r = self.api.post('/api/v1/tarifas/', {'Code': 'X', 'nombre': 'X', 'por_defecto': True, 'activa': False}, format='json')
        self.assertEqual(r.status_code, 400)
