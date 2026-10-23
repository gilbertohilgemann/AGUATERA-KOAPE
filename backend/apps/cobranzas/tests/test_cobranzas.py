"""Fase 6: pagos, aplicaciones, recibos, saldos y reversiones (pruebas obligatorias 9, 10, 11, 12 y 16)."""
import uuid
from decimal import Decimal as D

from apps.cobranzas.letras import en_letras
from apps.cobranzas.models import AplicacionPago, Pago, Recibo
from apps.facturacion.tests.test_facturas import BaseFacturas
from comun.pruebas.utilidades import admin_de, cliente_de, nueva_institucion, usuario_con_permisos


class BaseCobranzas(BaseFacturas):
    def credito(self, liquidaciones):
        return self.emitir(liquidaciones, 'credito')

    def cobrar(self, importe, aplicaciones=None, *, clave=None, forma='EFECTIVO', codigo=201, api=None, **extra):
        cuerpo = {'cliente': 'C1', 'importe': str(importe), 'forma_pago': forma, 'clave': clave or str(uuid.uuid4()),
                  **extra}
        if aplicaciones is not None:
            cuerpo['aplicaciones'] = [{'factura': f['referencia'], 'importe': str(i)} for f, i in aplicaciones]
        r = (api or self.api).post('/api/v1/recibos/', cuerpo, format='json')
        self.assertEqual(r.status_code, codigo, r.data)
        return r.data

    def factura(self, f):
        return self.api.get(f'/api/v1/facturas/{f["referencia"]}/').data


class ContadoTests(BaseCobranzas):
    def test_la_factura_contado_queda_pagada_con_su_forma_de_pago(self):
        f = self.emitir([self.oct])
        self.assertEqual((D(f['pagado']), D(f['saldo']), f['estado_cobro']), (self.oct.total, D('0'), 'pagada'))
        self.assertEqual([(p['origen'], p['forma_pago'], p['estado']) for p in f['pagos']],
                         [('contado', 'Efectivo', 'vigente')])
        pago = Pago.objects.get()
        self.assertEqual((pago.origen, pago.importe, pago.cliente.Code), ('contado', self.oct.total, 'C1'))

    def test_contado_exige_forma_de_pago_y_referencia(self):
        r = self.api.post('/api/v1/facturas/', {'cliente': 'C1', 'liquidaciones': [self.oct.numero],
                                                'condicion': 'contado'}, format='json')
        self.assertEqual(r.data['codigo'], 'forma_pago_requerida')
        self.assertEqual(self.emitir([self.oct], forma_pago='TRANSFERENCIA', codigo=400)['codigo'], 'falta_referencia')
        f = self.emitir([self.oct], forma_pago='TRANSFERENCIA', referencia_externa='TRF-991')
        self.assertEqual(f['pagos'][0]['referencia_externa'], 'TRF-991')
        self.assertEqual(Pago.objects.count(), 1)  # los intentos fallidos no dejaron nada

    def test_anular_contado_revierte_su_pago_y_no_se_cobra_con_recibo(self):
        f = self.emitir([self.oct])
        self.assertEqual(self.cobrar(1000, [(f, 1000)], codigo=400)['codigo'], 'supera_saldo')
        r = self.api.post(f'/api/v1/facturas/{f["referencia"]}/anular/', {'motivo': 'Error de carga'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        pago = Pago.objects.get()
        self.assertEqual(pago.estado, 'revertido')  # el pago original se conserva, revertido
        self.assertIn('anulada', pago.motivo_reversion)
        self.assertEqual(AplicacionPago.objects.get().estado, 'revertida')


class RecibosTests(BaseCobranzas):
    def test_una_factura_recibe_varios_pagos_parciales(self):  # prueba obligatoria 9
        f = self.credito([self.oct])  # 44.800
        r1 = self.cobrar(20000, [(f, 20000)])
        self.assertEqual((r1['numero'], D(r1['saldo_restante'])), ('0000001', D('24800')))
        self.assertEqual(self.factura(f)['estado_cobro'], 'parcial')
        r2 = self.cobrar(24800, [(f, 24800)])
        self.assertEqual(r2['numero'], '0000002')
        datos = self.factura(f)
        self.assertEqual((D(datos['saldo']), datos['estado_cobro'], len(datos['pagos'])), (D('0'), 'pagada', 2))
        self.assertEqual(self.cobrar(1, [(f, 1)], codigo=400)['codigo'], 'supera_saldo')

    def test_un_pago_se_distribuye_entre_varias_facturas(self):  # prueba obligatoria 10
        f1 = self.credito([self.oct])     # 44.800
        f2 = self.credito([self.otra])    # CX2
        total2 = D(f2['total'])
        r = self.cobrar(D('44800') + total2 - 1000, [(f1, 44800), (f2, total2 - 1000)])
        self.assertEqual([(a['numero'], D(a['importe'])) for a in r['aplicaciones']],
                         [(f1['numero'], D('44800')), (f2['numero'], total2 - 1000)])
        self.assertEqual(D(r['saldo_restante']), D('1000'))
        self.assertEqual(self.factura(f1)['estado_cobro'], 'pagada')
        self.assertEqual(D(self.factura(f2)['saldo']), D('1000'))

    def test_no_se_aplica_mas_que_lo_disponible(self):  # prueba obligatoria 11
        f1 = self.credito([self.oct])
        f2 = self.credito([self.otra])
        self.assertEqual(self.cobrar(50000, [(f1, 50000)], codigo=400)['codigo'], 'supera_saldo')
        self.assertEqual(self.cobrar(10000, [(f1, 5000)], codigo=400)['codigo'], 'reparto_distinto')
        self.assertEqual(self.cobrar(10000, [(f1, 5000), (f2, 6000)], codigo=400)['codigo'], 'reparto_distinto')
        total = D('44800') + D(f2['total'])
        self.assertEqual(self.cobrar(total + 1, codigo=400)['codigo'], 'supera_saldo')
        self.cobrar(10000, [(f1, 0)], codigo=400)
        self.cobrar(-5, [(f1, -5)], codigo=400)
        self.cobrar('100.50', [(f1, '100.50')], codigo=400)
        self.assertFalse(Pago.objects.exists())

    def test_reintento_con_la_misma_clave_no_duplica(self):  # prueba obligatoria 12
        f = self.credito([self.oct])
        clave = str(uuid.uuid4())
        r1 = self.cobrar(10000, [(f, 10000)], clave=clave)
        r2 = self.cobrar(10000, [(f, 10000)], clave=clave)
        self.assertEqual(r1['numero'], r2['numero'])
        self.assertEqual((Pago.objects.count(), Recibo.objects.count()), (1, 1))
        self.assertEqual(D(self.factura(f)['saldo']), D('34800'))
        self.assertEqual(self.cobrar(5000, [(f, 5000)], clave=clave, codigo=400)['codigo'], 'clave_repetida')

    def test_reparto_automatico_o_manual_segun_la_institucion(self):
        f1 = self.credito([self.oct])
        f2 = self.credito([self.otra])
        self.assertEqual(self.cobrar(50000, codigo=400)['codigo'], 'reparto_requerido')  # manual por defecto
        self.api.patch('/api/v1/institucion/', {'aplicacion_pagos': 'automatica'}, format='json')
        r = self.cobrar(50000)
        # Primero la más antigua (misma fecha: menor número), y el resto a la siguiente.
        self.assertEqual([(a['numero'], D(a['importe'])) for a in r['aplicaciones']],
                         [(f1['numero'], D('44800')), (f2['numero'], D('5200'))])
        cuenta = self.api.get('/api/v1/cobranzas/estado-cuenta/?cliente=C1').data
        self.assertEqual((cuenta['aplicacion_pagos'], [f['numero'] for f in cuenta['facturas']]),
                         ('automatica', [f2['numero']]))

    def test_anular_recibo_conserva_el_original_y_devuelve_el_saldo(self):  # prueba obligatoria 16
        f = self.credito([self.oct])
        r = self.cobrar(30000, [(f, 30000)])
        url = f'/api/v1/recibos/{r["numero"]}'
        self.assertEqual(self.api.post(f'{url}/anular/', {'motivo': ''}, format='json').status_code, 400)
        anulado = self.api.post(f'{url}/anular/', {'motivo': 'Cheque rechazado'}, format='json').data
        self.assertEqual((anulado['estado'], anulado['motivo_anulacion']), ('anulado', 'Cheque rechazado'))
        self.assertEqual(anulado['aplicaciones'][0]['estado'], 'revertida')  # sigue ahí, revertida
        pago = Pago.objects.get()
        self.assertEqual((pago.estado, pago.importe), ('revertido', D('30000')))
        self.assertEqual(D(self.factura(f)['saldo']), D('44800'))
        self.assertEqual(self.api.post(f'{url}/anular/', {'motivo': 'otra vez'}, format='json').status_code, 400)
        historial = self.api.get('/api/v1/pagos/?cliente=C1').data['results']
        self.assertEqual([(p['estado'], p['recibo']) for p in historial], [('revertido', r['numero'])])

    def test_factura_con_recibo_no_se_anula(self):
        f = self.credito([self.oct])
        r = self.cobrar(1000, [(f, 1000)])
        respuesta = self.api.post(f'/api/v1/facturas/{f["referencia"]}/anular/', {'motivo': 'x'}, format='json')
        self.assertEqual(respuesta.data['codigo'], 'tiene_recibos')
        self.api.post(f'/api/v1/recibos/{r["numero"]}/anular/', {'motivo': 'error'}, format='json')
        respuesta = self.api.post(f'/api/v1/facturas/{f["referencia"]}/anular/', {'motivo': 'x'}, format='json')
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(self.api.get('/api/v1/cobranzas/estado-cuenta/?cliente=C1').data['facturas'], [])

    def test_forma_de_pago_desactivada_o_sin_referencia(self):
        f = self.credito([self.oct])
        self.assertEqual(self.cobrar(1000, [(f, 1000)], forma='POS', codigo=400)['codigo'], 'falta_referencia')
        self.api.patch('/api/v1/formas-pago/EFECTIVO/', {'activa': False}, format='json')
        self.cobrar(1000, [(f, 1000)], codigo=400)
        r = self.cobrar(1000, [(f, 1000)], forma='POS', referencia_externa='VOUCHER 1')
        self.assertEqual((r['forma_pago'], r['referencia_externa']), ('POS (tarjeta)', 'VOUCHER 1'))
        nueva = self.api.post('/api/v1/formas-pago/', {'Code': 'giros', 'nombre': 'Giros Tigo', 'tipo': 'otro',
                                                       'requiere_referencia': True}, format='json')
        self.assertEqual((nueva.status_code, nueva.data['Code']), (201, 'GIROS'))
        self.assertEqual(self.api.post('/api/v1/formas-pago/', {'Code': 'GIROS', 'nombre': 'x'},
                                       format='json').status_code, 400)

    def test_deudas_del_cobrador_descuentan_lo_pagado(self):
        f = self.credito([self.oct])
        self.cobrar(4800, [(f, 4800)])
        deudas = self.cob.get(f'/api/v1/cobrador/lecturas/{self.nov.lectura.comprobante}/').data['deudas']
        self.assertEqual([(D(x['pagado']), D(x['saldo'])) for x in deudas['facturas']], [(D('4800'), D('40000'))])
        self.cobrar(40000, [(f, 40000)])
        deudas = self.cob.get(f'/api/v1/cobrador/lecturas/{self.nov.lectura.comprobante}/').data['deudas']
        self.assertEqual(deudas['facturas'], [])

    def test_pdf_y_letras(self):
        f = self.credito([self.oct])
        r = self.cobrar(44800, [(f, 44800)])
        pdf = self.api.get(f'/api/v1/recibos/{r["numero"]}/pdf/')
        self.assertEqual((pdf.status_code, pdf.content[:5]), (200, b'%PDF-'))
        self.assertEqual(en_letras(44800), 'cuarenta y cuatro mil ochocientos')
        self.assertEqual(en_letras(1_521_000), 'un millón quinientos veintiún mil')

    def test_permisos_y_aislamiento(self):
        f = self.credito([self.oct])
        r = self.cobrar(1000, [(f, 1000)])
        usuario_con_permisos(self.a, 'consulta', ['cobranzas.consultar'])
        consulta = cliente_de(self.a, 'consulta')
        self.assertEqual(consulta.get(f'/api/v1/recibos/{r["numero"]}/').status_code, 200)
        self.assertEqual(consulta.get('/api/v1/pagos/').status_code, 200)
        self.cobrar(1000, [(f, 1000)], api=consulta, codigo=403)
        usuario_con_permisos(self.a, 'cajero', ['cobranzas.registrar', 'caja.operar'])
        cajero = cliente_de(self.a, 'cajero')
        self.assertEqual(self.cobrar(1000, [(f, 1000)], api=cajero, codigo=400)['codigo'], 'caja_cerrada')
        self.api.post('/api/v1/cajas/', {'Code': 'CAJA2', 'nombre': 'Ventanilla 2'}, format='json')
        cajero.post('/api/v1/caja/mi-sesion/', {'caja': 'CAJA2', 'saldo_inicial': '0'}, format='json')
        self.cobrar(1000, [(f, 1000)], api=cajero)
        self.assertEqual(cajero.post(f'/api/v1/recibos/{r["numero"]}/anular/', {'motivo': 'x'},
                                     format='json').status_code, 403)
        # Otra institución: no ve recibos, pagos ni el estado de cuenta, y no aplica pagos a facturas ajenas.
        b = nueva_institucion('JUNTA-B')
        admin_de(b)
        otra = cliente_de(b)
        self.assertEqual(otra.get(f'/api/v1/recibos/{r["numero"]}/').status_code, 404)
        self.assertEqual(otra.get('/api/v1/pagos/').data['count'], 0)
        self.assertEqual(otra.get('/api/v1/cobranzas/estado-cuenta/?cliente=C1').status_code, 404)
        from apps.padron import servicios as padron
        padron.crear_cliente(institucion=b, datos={'Code': 'C1', 'nombre': 'Homónimo'})
        respuesta = otra.post('/api/v1/recibos/', {'cliente': 'C1', 'importe': '1000', 'forma_pago': 'EFECTIVO',
                                                   'clave': 'k1', 'aplicaciones': [{'factura': f['referencia'],
                                                                                    'importe': '1000'}]}, format='json')
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(Pago.objects.filter(institucion=b).count(), 0)


class RevisionTests(BaseCobranzas):
    def test_reintento_que_espero_el_bloqueo_devuelve_el_mismo_recibo(self):
        # Simula el reintento que entra a la transacción después de que el primero ya confirmó y agotó el saldo.
        from apps.cobranzas import servicios
        f = self.credito([self.oct])
        clave = str(uuid.uuid4())
        primero = self.cobrar(44800, [(f, 44800)], clave=clave)
        original = servicios._recibo_por_clave
        llamadas = []

        def sin_ver_la_primera_vez(institucion, c):
            llamadas.append(c)
            return None if len(llamadas) == 1 else original(institucion, c)
        servicios._recibo_por_clave = sin_ver_la_primera_vez
        try:
            segundo = self.cobrar(44800, [(f, 44800)], clave=clave)
        finally:
            servicios._recibo_por_clave = original
        self.assertEqual(primero['numero'], segundo['numero'])
        self.assertEqual(Recibo.objects.count(), 1)

    def test_clave_de_contado_o_con_otra_forma_no_se_reutiliza(self):
        f = self.emitir([self.oct])
        f2 = self.credito([self.otra])
        self.cobrar(1000, [(f2, 1000)], clave=f'contado:{f["referencia"]}', codigo=400)
        clave = str(uuid.uuid4())
        self.cobrar(1000, [(f2, 1000)], clave=clave)
        self.assertEqual(self.cobrar(1000, [(f2, 1000)], clave=clave, forma='POS', referencia_externa='V1',
                                     codigo=400)['codigo'], 'clave_repetida')

    def test_importe_grande_en_letras_completo_en_el_pdf(self):
        self.assertEqual(en_letras(777_777_777), 'setecientos setenta y siete millones setecientos setenta y siete '
                                                 'mil setecientos setenta y siete')


class FiltroDeudaTests(BaseCobranzas):
    """Padrón y mapa (sección 8.2): con deuda, al día y morosa, con definiciones explícitas (D50)."""

    def codes(self, deuda, api=None):
        r = (api or self.api).get(f'/api/v1/conexiones/?deuda={deuda}')
        self.assertEqual(r.status_code, 200, r.data)
        return sorted(c['Code'] for c in r.data['results'])

    def test_con_deuda_al_dia_y_morosa(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.facturacion.models import Factura
        # Consumos sin facturar ya son deuda (no mora).
        self.assertEqual((self.codes('con'), self.codes('al_dia'), self.codes('morosa')), (['CX1', 'CX2'], [], []))
        f = self.credito([self.oct, self.nov])
        self.assertEqual((self.codes('con'), self.codes('sin_facturar'), self.codes('morosa')),
                         (['CX1', 'CX2'], ['CX2'], []))                     # crédito que todavía no venció
        Factura.objects.filter(referencia=f['referencia']).update(
            fecha_vencimiento=timezone.localdate() - timedelta(days=1))
        self.assertEqual(self.codes('morosa'), ['CX1'])
        self.cobrar(D(f['total']), [(f, D(f['total']))])
        self.assertEqual((self.codes('al_dia'), self.codes('morosa')), (['CX1'], []))
        mapa = self.api.get('/api/v1/mapa/?deuda=con').data
        self.assertEqual([c['Code'] for c in mapa['conexiones']], ['CX2'])

    def test_factura_anulada_vuelve_a_consumo_sin_facturar_y_otra_institucion_no_cuenta(self):
        f = self.credito([self.oct, self.nov])
        self.assertEqual(self.codes('sin_facturar'), ['CX2'])
        r = self.api.post(f'/api/v1/facturas/{f["referencia"]}/anular/', {'motivo': 'Error de carga'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((self.codes('sin_facturar'), self.codes('morosa')), (['CX1', 'CX2'], []))
        otra = nueva_institucion('JUNTA-Z')
        admin_de(otra)
        self.assertEqual(cliente_de(otra).get('/api/v1/conexiones/?deuda=con').data['results'], [])

    def test_filtrar_por_deuda_exige_permiso_de_cobranzas(self):
        usuario_con_permisos(self.a, 'padron1', ['padron.consultar', 'mapa.ver'])
        api = cliente_de(self.a, 'padron1')
        self.assertEqual(api.get('/api/v1/conexiones/?deuda=con').status_code, 403)
        self.assertEqual(api.get('/api/v1/mapa/?deuda=con').status_code, 403)
        self.assertEqual(api.get('/api/v1/conexiones/').status_code, 200)
