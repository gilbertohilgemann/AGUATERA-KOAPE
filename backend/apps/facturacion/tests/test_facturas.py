"""
Pruebas de la Fase 5: facturación.

Casos obligatorios de la sección 21: 8 (una liquidación no se factura dos veces) y 13 (un timeout de facturación
electrónica no provoca una segunda emisión automática sin verificar el estado).
"""
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.facturacion import electronica
from apps.facturacion.models import (AsignacionFacturaLiquidacion, Factura, ProveedorFacturacion, RegistroIntegracion,
                                     SolicitudElectronica)
from apps.tarifas.models import Liquidacion
from apps.tarifas.tests.test_tarifas import BaseLiquidaciones
from comun.pruebas.utilidades import cliente_de, usuario_con_permisos

D = Decimal


class BaseFacturas(BaseLiquidaciones):
    def setUp(self):
        super().setUp()
        self.a.modalidad_facturacion = 'autoimpresa'
        self.a.ruc = '80012345-6'
        self.a.dias_vencimiento_credito = 15
        self.a.save()
        self.api.post('/api/v1/puntos-expedicion/', {'Code': 'CENTRAL', 'establecimiento': '001', 'punto': '001',
                                                     'nombre': 'Oficina'}, format='json')
        self.api.post('/api/v1/rangos-numeracion/', {'Code': 'FAC', 'punto': 'CENTRAL', 'tipo_documento': 'factura',
                                                     'timbrado': '12345678', 'desde': 1, 'hasta': 1000,
                                                     'vigencia_desde': '2026-01-01', 'vigencia_hasta': '2026-12-31'},
                      format='json')
        self.tarifa()
        self.recorrido('R10', '2026-10')
        self.recorrido('R11', '2026-11')
        self.oct = self.liquidacion_de(self.leer('R10', 'M1', '115')['comprobante'])   # 44.800
        self.nov = self.liquidacion_de(self.leer('R11', 'M1', '120')['comprobante'])   # consumo 5 → 28.000
        self.otra = self.liquidacion_de(self.leer('R10', 'M2', '110')['comprobante'])  # CX2, mismo cliente
        # Fase 7: para cobrar hace falta la caja abierta.
        r = self.api.post('/api/v1/caja/mi-sesion/', {'caja': 'CAJA1', 'saldo_inicial': '100000'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)

    def emitir(self, liquidaciones, condicion='contado', codigo=201, api=None, **extra):
        cuerpo = {'cliente': 'C1', 'liquidaciones': [q.numero for q in liquidaciones], 'condicion': condicion,
                  **({'forma_pago': 'EFECTIVO'} if condicion == 'contado' else {}), **extra}
        r = (api or self.api).post('/api/v1/facturas/', cuerpo, format='json')
        self.assertEqual(r.status_code, codigo, r.data)
        return r.data


class FacturaTests(BaseFacturas):
    def test_pendientes_del_cliente_y_factura_con_varias_liquidaciones(self):
        r = self.api.get('/api/v1/facturacion/pendientes/?cliente=c1')
        self.assertEqual(sorted(p['numero'] for p in r.data['pendientes']), sorted([self.oct.numero, self.nov.numero,
                                                                                     self.otra.numero]))
        f = self.emitir([self.oct, self.nov])
        self.assertEqual((f['numero'], f['timbrado'], f['estado'], f['condicion']), ('001-001-0000001', '12345678',
                                                                                       'emitida', 'contado'))
        self.assertEqual(D(f['total']), self.oct.total + self.nov.total)
        # Columnas con IVA incluido y liquidación del IVA que cuadran al guaraní.
        self.assertEqual(D(f['subtotal_iva10']), self.oct.subtotal_iva10 + self.oct.iva10 + self.nov.subtotal_iva10 + self.nov.iva10)
        self.assertEqual(D(f['subtotal_exento']) + D(f['subtotal_iva5']) + D(f['subtotal_iva10']), D(f['total']))
        self.assertEqual(sum(D(l['total_linea']) for l in f['lineas']), D(f['total']))
        self.assertEqual(sum(D(l['importe_iva']) for l in f['lineas']), D(f['iva10']))
        self.assertNotIn('id', f)
        pendientes = self.api.get('/api/v1/facturacion/pendientes/?cliente=C1').data['pendientes']
        self.assertEqual([p['numero'] for p in pendientes], [self.otra.numero])
        segunda = self.emitir([self.otra], 'credito')
        self.assertEqual((segunda['numero'], segunda['fecha_vencimiento']),
                         ('001-001-0000002', str(timezone.localdate() + timedelta(days=15))))

    def test_una_liquidacion_no_se_factura_dos_veces(self):
        self.emitir([self.oct])
        r = self.emitir([self.oct, self.nov], codigo=400)
        self.assertEqual(r['codigo'], 'ya_facturada')
        self.assertEqual(Factura.objects.count(), 1)  # todo o nada: no se emitió la segunda
        f = Factura.objects.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AsignacionFacturaLiquidacion.objects.create(institucion=self.a, factura=f, liquidacion=self.oct, importe=1)

    def test_anular_libera_las_liquidaciones_y_la_lectura_facturada_no_se_corrige(self):
        f = self.emitir([self.nov])  # la última lectura del medidor (las anteriores ya no se corrigen)
        lectura = self.nov.lectura.comprobante
        r = self.api.post(f'/api/v1/lecturas/{lectura}/corregir/', {'lectura_actual': '116', 'motivo': 'x'}, format='json')
        self.assertEqual(r.data['codigo'], 'ya_facturada')
        url = f'/api/v1/facturas/{f["referencia"]}'
        self.assertEqual(self.api.post(f'{url}/anular/', {'motivo': ''}, format='json').status_code, 400)
        r = self.api.post(f'{url}/anular/', {'motivo': 'Error en el nombre'}, format='json')
        self.assertEqual(r.data['estado'], 'anulada')
        self.assertEqual(self.api.delete(f'{url}/').status_code, 405)
        nueva = self.emitir([self.nov])  # la liquidación volvió a quedar para facturar, con otro número
        self.assertEqual(nueva['numero'], '001-001-0000002')
        self.assertEqual(Factura.objects.count(), 2)

    def test_reglas_de_emision(self):
        # Otra persona: no se factura una liquidación de una conexión de otro titular.
        from apps.padron import servicios as padron
        otro = padron.crear_cliente(institucion=self.a, datos={'Code': 'C2', 'nombre': 'Otro'})
        r = self.api.post('/api/v1/facturas/', {'cliente': 'C2', 'liquidaciones': [self.oct.numero], 'condicion': 'contado'},
                          format='json')
        self.assertEqual(r.status_code, 400)
        # Liquidación anulada.
        lectura = self.otra.lectura.comprobante
        self.api.post(f'/api/v1/lecturas/{lectura}/anular/', {'motivo': 'x'}, format='json')
        self.emitir([self.otra], codigo=400)
        # Sin modalidad habilitada no se emite.
        self.a.modalidad_facturacion = 'no_configurada'
        self.a.save()
        self.assertEqual(self.emitir([self.oct], codigo=400)['codigo'], 'modalidad_no_configurada')
        self.assertTrue(otro)

    def test_pdf_permisos_y_aislamiento(self):
        f = self.emitir([self.oct])
        url = f'/api/v1/facturas/{f["referencia"]}'
        pdf = self.api.get(f'{url}/pdf/')
        self.assertEqual((pdf.status_code, pdf['Content-Type'], pdf.content[:5]), (200, 'application/pdf', b'%PDF-'))
        usuario_con_permisos(self.a, 'consulta', ['facturacion.consultar'])
        consulta = cliente_de(self.a, 'consulta')
        self.assertEqual(consulta.get(f'{url}/').status_code, 200)
        self.assertEqual(consulta.post(f'{url}/anular/', {'motivo': 'x'}, format='json').status_code, 403)
        self.assertEqual(consulta.post('/api/v1/facturas/', {}, format='json').status_code, 403)
        usuario_con_permisos(self.a, 'cajero', ['facturacion.emitir'])
        cajero = cliente_de(self.a, 'cajero')
        self.assertEqual(cajero.post(f'{url}/anular/', {'motivo': 'x'}, format='json').status_code, 403)
        from apps.plataforma.models import Institucion
        from comun.pruebas.utilidades import admin_de, nueva_institucion
        b = nueva_institucion('JUNTA-B')
        admin_de(b)
        self.assertEqual(cliente_de(b).get(f'{url}/').status_code, 404)
        self.assertTrue(Institucion.objects.exists())

    def test_deudas_para_el_cobrador_despues_de_la_lectura(self):
        self.emitir([self.oct], 'credito')
        r = self.cob.get(f'/api/v1/cobrador/lecturas/{self.nov.lectura.comprobante}/')
        deudas = r.data['deudas']
        self.assertEqual([p['liquidacion'] for p in deudas['pendientes_de_facturar']], [self.nov.numero])
        self.assertEqual([(f['numero'], D(f['saldo'])) for f in deudas['facturas']], [('001-001-0000001', self.oct.total)])

    def test_deudas_solo_la_parte_de_la_conexion(self):
        # Una factura con dos conexiones: cada conexión ve solo lo suyo (no el total de la factura).
        self.emitir([self.oct, self.otra], 'credito')
        deudas = self.cob.get(f'/api/v1/cobrador/lecturas/{self.nov.lectura.comprobante}/').data['deudas']
        self.assertEqual([D(f['saldo']) for f in deudas['facturas']], [self.oct.total])

    def test_buscar_por_numero(self):
        self.emitir([self.oct])
        for texto, cantidad in (('001-001-', 0), ('001-001-0000001', 1), ('1', 1), ('001-002-0000001', 0), ('9999999999999', 0)):
            r = self.api.get('/api/v1/facturas/', {'buscar': texto})
            self.assertEqual((texto, r.status_code, r.data['count']), (texto, 200, cantidad))

    def test_sin_timbrado_no_se_autoimprime(self):
        self.api.patch('/api/v1/rangos-numeracion/FAC/', {'activo': False}, format='json')
        self.api.post('/api/v1/rangos-numeracion/', {'Code': 'SIN', 'punto': 'CENTRAL', 'tipo_documento': 'factura',
                                                     'desde': 1001, 'hasta': 2000}, format='json')
        self.emitir([self.oct], codigo=400)
        self.assertFalse(Factura.objects.exists())


# --- Electrónica ---------------------------------------------------------------------------------------

class AdaptadorDePrueba(electronica.Adaptador):
    """Solo para pruebas: simula un proveedor (no existe en el sistema real)."""

    respuestas: list = []
    enviados: list = []

    def enviar(self, id_solicitud, documento):
        AdaptadorDePrueba.enviados.append(id_solicitud)
        respuesta = AdaptadorDePrueba.respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    def consultar(self, id_solicitud, numero_proveedor):
        respuesta = AdaptadorDePrueba.respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


class ElectronicaTests(BaseFacturas):
    def setUp(self):
        super().setUp()
        self.a.modalidad_facturacion = 'electronica'
        self.a.save()
        electronica.registrar_adaptador('prueba', AdaptadorDePrueba)
        AdaptadorDePrueba.respuestas, AdaptadorDePrueba.enviados = [], []

    def tearDown(self):
        electronica.quitar_adaptador('prueba')
        super().tearDown()

    def proveedor(self):
        return ProveedorFacturacion.objects.create(institucion=self.a, nombre='Proveedor de prueba', adaptador='prueba')

    def test_sin_proveedor_conectado_no_se_emite(self):
        self.assertEqual(self.emitir([self.oct], codigo=400)['codigo'], 'proveedor_no_configurado')
        ProveedorFacturacion.objects.create(institucion=self.a, nombre='X', adaptador='no-programado')
        self.assertEqual(self.emitir([self.oct], codigo=400)['codigo'], 'proveedor_no_configurado')
        self.assertFalse(Factura.objects.exists())

    def test_emision_aprobada(self):
        self.proveedor()
        AdaptadorDePrueba.respuestas = [electronica.Resultado('aprobada', numero_proveedor='P-1', cdc='0' * 44,
                                                              respuesta={'ok': True})]
        f = self.emitir([self.oct])
        self.assertEqual((f['estado'], f['cdc'], f['electronica']['estado']), ('emitida', '0' * 44, 'aprobada'))
        self.assertEqual(RegistroIntegracion.objects.filter(operacion='enviar').count(), 1)

    def test_timeout_no_reemite_a_ciegas(self):
        self.proveedor()
        AdaptadorDePrueba.respuestas = [electronica.ErrorTemporal('timeout')]
        f = self.emitir([self.oct])
        self.assertEqual((f['estado'], f['electronica']['estado']), ('en_tramite', 'desconocido'))
        url = f'/api/v1/facturas/{f["referencia"]}'
        # Reintentar a ciegas está prohibido: hay que consultar.
        self.assertEqual(self.api.post(f'{url}/reintentar/').status_code, 400)
        self.assertEqual(len(AdaptadorDePrueba.enviados), 1)
        AdaptadorDePrueba.respuestas = [electronica.Resultado('aprobada', cdc='1' * 44)]
        r = self.api.post(f'{url}/consultar-estado/')
        self.assertEqual((r.data['estado'], r.data['cdc']), ('emitida', '1' * 44))
        self.assertEqual(len(AdaptadorDePrueba.enviados), 1)  # nunca se envió dos veces
        self.assertEqual(SolicitudElectronica.objects.get().intentos, 1)

    def test_error_recuperable_se_reintenta_con_el_mismo_identificador(self):
        self.proveedor()
        AdaptadorDePrueba.respuestas = [electronica.ErrorProveedor('servicio caído'),
                                        electronica.Resultado('aprobada', cdc='2' * 44)]
        f = self.emitir([self.oct])
        self.assertEqual(f['electronica']['estado'], 'error_recuperable')
        r = self.api.post(f'/api/v1/facturas/{f["referencia"]}/reintentar/')
        self.assertEqual(r.data['estado'], 'emitida')
        self.assertEqual(len(set(AdaptadorDePrueba.enviados)), 1)  # mismo id_solicitud (idempotencia)

    def test_rechazada_libera_las_liquidaciones(self):
        self.proveedor()
        AdaptadorDePrueba.respuestas = [electronica.Resultado('rechazada', mensaje='RUC del receptor inválido')]
        f = self.emitir([self.oct])
        self.assertEqual((f['estado'], f['electronica']['ultimo_error']), ('rechazada', 'RUC del receptor inválido'))
        pendientes = self.api.get('/api/v1/facturacion/pendientes/?cliente=C1').data['pendientes']
        self.assertIn(self.oct.numero, [p['numero'] for p in pendientes])
        self.assertEqual(Liquidacion.objects.get(pk=self.oct.pk).asignaciones.filter(estado='vigente').count(), 0)
        # Era contado: su pago queda revertido (no se cobra una factura rechazada).
        from apps.cobranzas.models import Pago
        self.assertEqual(list(Pago.objects.values_list('estado', flat=True)), ['revertido'])

    def test_error_inesperado_del_adaptador_no_reenvia(self):
        # Un corte cualquiera (no previsto por el adaptador): la factura existe y queda para CONSULTAR, no para reenviar.
        self.proveedor()
        AdaptadorDePrueba.respuestas = [ConnectionError('reset')]
        f = self.emitir([self.oct])
        self.assertEqual((f['estado'], f['electronica']['estado']), ('en_tramite', 'desconocido'))
        self.assertEqual(self.api.post(f'/api/v1/facturas/{f["referencia"]}/reintentar/').status_code, 400)
        self.assertEqual(len(AdaptadorDePrueba.enviados), 1)

    def test_estado_no_reconocido_queda_desconocido(self):
        self.proveedor()
        AdaptadorDePrueba.respuestas = [electronica.Resultado('ok')]
        self.assertEqual(self.emitir([self.oct])['electronica']['estado'], 'desconocido')

    def test_envio_en_curso_no_se_vuelve_a_enviar(self):
        # Si otro cajero ya tomó el envío (estado «enviada»), «Reintentar» no llama al proveedor.
        self.proveedor()
        AdaptadorDePrueba.respuestas = [electronica.ErrorProveedor('caído')]
        f = self.emitir([self.oct])
        SolicitudElectronica.objects.update(estado='enviada')
        self.assertEqual(self.api.post(f'/api/v1/facturas/{f["referencia"]}/reintentar/').status_code, 400)
        self.assertEqual(len(AdaptadorDePrueba.enviados), 1)

    def test_consulta_fallida_y_luego_rechazo(self):
        self.proveedor()
        AdaptadorDePrueba.respuestas = [electronica.ErrorTemporal('timeout'), electronica.ErrorTemporal('otra vez'),
                                        electronica.Resultado('rechazada', mensaje='No recibida')]
        f = self.emitir([self.oct])
        url = f'/api/v1/facturas/{f["referencia"]}/consultar-estado/'
        self.assertEqual(self.api.post(url).status_code, 400)
        self.assertEqual(self.api.post(url).data['estado'], 'rechazada')

    def test_no_se_anula_una_electronica(self):
        self.proveedor()
        AdaptadorDePrueba.respuestas = [electronica.Resultado('aprobada', cdc='3' * 44)]
        f = self.emitir([self.oct])
        r = self.api.post(f'/api/v1/facturas/{f["referencia"]}/anular/', {'motivo': 'x'}, format='json')
        self.assertEqual(r.status_code, 400)
