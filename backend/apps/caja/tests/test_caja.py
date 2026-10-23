"""Fase 7: caja y gastos (pruebas obligatorias 14, 15 y 16 y criterio: cada ingreso y egreso se refleja una sola vez)."""
import io
from decimal import Decimal as D

from apps.caja.models import MovimientoCaja, SesionCaja
from apps.cobranzas.tests.test_cobranzas import BaseCobranzas
from comun.pruebas.utilidades import admin_de, cliente_de, nueva_institucion, usuario_con_permisos

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64


class BaseCaja(BaseCobranzas):
    def mi_caja(self, api=None):
        return (api or self.api).get('/api/v1/caja/mi-sesion/').data

    def sesion(self, api=None):
        return self.mi_caja(api)['sesion']

    def resumen(self, api=None):
        return {f['forma_pago']: (D(f['ingresos']), D(f['egresos']), D(f['esperado'])) for f in self.sesion(api)['resumen']}

    def cerrar(self, referencia, declarados, observaciones='', codigo=200, api=None):
        r = (api or self.api).post(f'/api/v1/sesiones-caja/{referencia}/cerrar/', {
            'declarados': [{'forma_pago': k, 'importe': str(v)} for k, v in declarados.items()],
            'observaciones': observaciones}, format='json')
        self.assertEqual(r.status_code, codigo, r.data)
        return r.data

    def gasto(self, importe=15000, forma='EFECTIVO', codigo=201, api=None, **extra):
        r = (api or self.api).post('/api/v1/gastos/', {
            'fecha': '2026-10-21', 'motivo': 'Repuesto de bomba', 'importe': str(importe), 'categoria': 'MANTENIMIENTO',
            'forma_pago': forma, 'beneficiario': 'Ferretería San José', 'responsable': 'Juan', **extra}, format='json')
        self.assertEqual(r.status_code, codigo, r.data)
        return r.data


class SesionTests(BaseCaja):
    def test_sin_caja_abierta_no_se_cobra(self):
        sesion = self.sesion()
        self.cerrar(sesion['referencia'], {'EFECTIVO': 100000})
        self.assertEqual(self.emitir([self.oct], codigo=400)['codigo'], 'caja_cerrada')
        f = self.credito([self.oct])
        self.assertEqual(self.cobrar(1000, [(f, 1000)], codigo=400)['codigo'], 'caja_cerrada')
        self.assertEqual(MovimientoCaja.objects.count(), 0)

    def test_cada_cobro_entra_una_vez_y_los_medios_no_se_suman(self):
        self.emitir([self.oct])                                                    # contado efectivo 44.800
        f = self.credito([self.otra])
        clave = 'clave-unica-1'
        self.cobrar(5000, [(f, 5000)], forma='TRANSFERENCIA', referencia_externa='T-1', clave=clave)
        self.cobrar(5000, [(f, 5000)], forma='TRANSFERENCIA', referencia_externa='T-1', clave=clave)  # reintento
        self.assertEqual(MovimientoCaja.objects.filter(origen='cobro').count(), 2)
        resumen = self.resumen()
        self.assertEqual(resumen['EFECTIVO'], (D('44800'), D('0'), D('144800')))   # 100.000 iniciales + contado
        self.assertEqual(resumen['TRANSFERENCIA'], (D('5000'), D('0'), D('5000')))  # aparte: no es dinero en caja

    def test_una_sesion_por_cajero_y_por_caja(self):
        r = self.api.post('/api/v1/caja/mi-sesion/', {'caja': 'CAJA1', 'saldo_inicial': '0'}, format='json')
        self.assertEqual(r.data['codigo'], 'ya_abierta')
        usuario_con_permisos(self.a, 'cajero', ['caja.operar'])
        cajero = cliente_de(self.a, 'cajero')
        r = cajero.post('/api/v1/caja/mi-sesion/', {'caja': 'CAJA1', 'saldo_inicial': '0'}, format='json')
        self.assertEqual(r.data['codigo'], 'caja_ocupada')
        self.assertEqual(self.mi_caja(cajero)['cajas_libres'], [])
        self.assertEqual(cajero.post('/api/v1/caja/mi-sesion/', {'caja': 'CAJA1', 'saldo_inicial': '-5'},
                                     format='json').status_code, 400)

    def test_cierre_con_y_sin_diferencias_y_la_sesion_cerrada_no_se_altera(self):  # prueba obligatoria 14
        self.emitir([self.oct])
        ref = self.sesion()['referencia']
        self.assertEqual(self.cerrar(ref, {}, codigo=400)['codigo'], 'falta_declarar')
        self.assertEqual(self.cerrar(ref, {'EFECTIVO': 144000}, codigo=400)['codigo'], 'explicar_diferencia')
        cerrada = self.cerrar(ref, {'EFECTIVO': 144000}, 'Faltan 800: vuelto mal dado')
        self.assertEqual(cerrada['estado'], 'en_revision')
        self.assertEqual([(d['forma_pago'], D(d['diferencia'])) for d in cerrada['declaraciones']],
                         [('EFECTIVO', D('-800'))])
        self.cerrar(ref, {'EFECTIVO': 144800}, codigo=400)                    # no se cierra dos veces
        self.assertIsNone(self.sesion())
        movimientos = MovimientoCaja.objects.count()
        f = self.credito([self.otra])
        self.cobrar(1000, [(f, 1000)], codigo=400)                            # sin caja abierta no entra nada
        self.assertEqual(MovimientoCaja.objects.count(), movimientos)
        url = f'/api/v1/sesiones-caja/{ref}/revisar/'
        self.assertEqual(self.api.post(url, {'comentario': ''}, format='json').status_code, 400)
        revisada = self.api.post(url, {'comentario': 'Se descontó al cajero'}, format='json').data
        self.assertEqual((revisada['estado'], revisada['revisada_por']), ('cerrada', 'admin'))
        pdf = self.api.get(f'/api/v1/sesiones-caja/{ref}/pdf/')
        self.assertEqual((pdf.status_code, pdf.content[:5]), (200, b'%PDF-'))

    def test_reversion_despues_del_cierre_va_a_la_caja_abierta_y_conserva_el_original(self):  # prueba 16
        f = self.credito([self.oct])
        r = self.cobrar(20000, [(f, 20000)])
        primera = self.sesion()['referencia']
        self.cerrar(primera, {'EFECTIVO': 120000})
        url = f'/api/v1/recibos/{r["numero"]}/anular/'
        self.assertEqual(self.api.post(url, {'motivo': 'Error'}, format='json').data['codigo'], 'caja_cerrada')
        self.api.post('/api/v1/caja/mi-sesion/', {'caja': 'CAJA1', 'saldo_inicial': '0'}, format='json')
        self.assertEqual(self.api.post(url, {'motivo': 'Error'}, format='json').status_code, 200)
        original = MovimientoCaja.objects.get(origen='cobro')
        reversion = MovimientoCaja.objects.get(origen='reversion_cobro')
        self.assertEqual((original.sesion.referencia, original.importe, original.tipo), (primera, D('20000'), 'ingreso'))
        self.assertEqual((reversion.original, reversion.tipo, reversion.importe), (original, 'egreso', D('20000')))
        self.assertNotEqual(reversion.sesion.referencia, primera)
        self.assertEqual(SesionCaja.objects.get(referencia=primera).estado, 'cerrada')  # la cerrada no cambió
        self.assertEqual(self.resumen()['EFECTIVO'], (D('0'), D('20000'), D('-20000')))

    def test_anular_contado_con_la_caja_abierta_compensa_en_la_misma_sesion(self):
        f = self.emitir([self.oct])
        self.api.post(f'/api/v1/facturas/{f["referencia"]}/anular/', {'motivo': 'Error'}, format='json')
        self.assertEqual(self.resumen()['EFECTIVO'], (D('44800'), D('44800'), D('100000')))

    def test_quien_opera_ve_solo_sus_sesiones(self):
        usuario_con_permisos(self.a, 'cajero', ['caja.operar'])
        cajero = cliente_de(self.a, 'cajero')
        self.assertEqual(cajero.get('/api/v1/sesiones-caja/').data['count'], 0)
        ref = self.sesion()['referencia']
        self.assertEqual(cajero.get(f'/api/v1/sesiones-caja/{ref}/').status_code, 404)
        self.assertEqual(cajero.post(f'/api/v1/sesiones-caja/{ref}/cerrar/', {}, format='json').status_code, 404)
        self.assertEqual(self.api.get('/api/v1/sesiones-caja/').data['count'], 1)
        b = nueva_institucion('JUNTA-B')
        admin_de(b)
        self.assertEqual(cliente_de(b).get(f'/api/v1/sesiones-caja/{ref}/').status_code, 404)


class GastoTests(BaseCaja):
    def test_un_gasto_confirmado_genera_un_unico_egreso(self):  # prueba obligatoria 15
        g = self.gasto()
        self.assertEqual(g['estado'], 'registrado')
        self.assertEqual(MovimientoCaja.objects.count(), 0)                 # registrado no mueve la caja
        url = f'/api/v1/gastos/{g["referencia"]}'
        confirmado = self.api.post(f'{url}/confirmar/').data
        self.api.post(f'{url}/confirmar/')                                  # reintento: no duplica
        self.assertEqual((confirmado['estado'], confirmado['sesion']), ('confirmado', self.sesion()['referencia']))
        self.assertEqual(MovimientoCaja.objects.filter(origen='gasto').count(), 1)
        self.assertEqual(self.resumen()['EFECTIVO'], (D('0'), D('15000'), D('85000')))
        self.assertEqual(self.api.patch(f'{url}/', {'importe': '1'}, format='json').status_code, 400)
        anulado = self.api.post(f'{url}/anular/', {'motivo': 'Se devolvió el repuesto'}, format='json').data
        self.assertEqual(anulado['estado'], 'anulado')
        self.assertEqual(self.resumen()['EFECTIVO'], (D('15000'), D('15000'), D('100000')))
        self.assertEqual(MovimientoCaja.objects.get(origen='reversion_gasto').original.origen, 'gasto')

    def test_confirmar_exige_caja_y_permiso(self):
        usuario_con_permisos(self.a, 'auxiliar', ['gastos.registrar'])
        auxiliar = cliente_de(self.a, 'auxiliar')
        g = self.gasto(api=auxiliar)
        url = f'/api/v1/gastos/{g["referencia"]}'
        self.assertEqual(auxiliar.post(f'{url}/confirmar/').status_code, 403)
        usuario_con_permisos(self.a, 'tesorero', ['gastos.confirmar', 'caja.operar'])
        tesorero = cliente_de(self.a, 'tesorero')
        self.assertEqual(tesorero.post(f'{url}/confirmar/').data['codigo'], 'caja_cerrada')
        self.assertEqual(self.api.post(f'{url}/confirmar/').data['estado'], 'confirmado')

    def test_registrado_se_corrige_y_valida(self):
        g = self.gasto()
        url = f'/api/v1/gastos/{g["referencia"]}/'
        self.assertEqual(D(self.api.patch(url, {'importe': '20000'}, format='json').data['importe']), D('20000'))
        self.gasto(importe=0, codigo=400)
        self.gasto(motivo='  ', codigo=400)
        self.gasto(categoria='NO-EXISTE', codigo=400)
        self.api.patch('/api/v1/categorias-gasto/OTROS/', {'activa': False}, format='json')
        self.gasto(categoria='OTROS', codigo=400)

    def test_boleta_interna_y_adjuntos(self):
        g = self.gasto()
        url = f'/api/v1/gastos/{g["referencia"]}'
        r = self.api.post(f'{url}/adjuntos/', {'archivo': io.BytesIO(PNG), 'tipo': 'boleta_firmada'}, format='multipart')
        self.assertEqual(r.status_code, 400)                                  # primero la boleta
        boleta = self.api.post(f'{url}/boleta/').data['boleta']
        self.assertEqual(boleta['numero'], '0000001')
        self.assertEqual(self.api.post(f'{url}/boleta/').data['boleta']['numero'], '0000001')  # la misma
        pdf = self.api.get(f'{url}/boleta/pdf/')
        self.assertEqual((pdf.status_code, pdf.content[:5]), (200, b'%PDF-'))
        self.assertEqual(self.api.patch(f'{url}/', {'importe': '1'}, format='json').data['codigo'], 'tiene_boleta')
        self.assertEqual(self.api.patch(f'{url}/', {'observaciones': 'ok'}, format='json').status_code, 200)
        archivo = io.BytesIO(PNG)
        archivo.name = 'firmada.png'
        r = self.api.post(f'{url}/adjuntos/', {'archivo': archivo, 'tipo': 'boleta_firmada'}, format='multipart')
        self.assertEqual(r.status_code, 201, r.data)
        codigo = r.data['adjuntos'][0]['codigo']
        self.assertEqual(self.api.get(f'{url}/adjuntos/{codigo}/').status_code, 200)
        texto = io.BytesIO(b'no es imagen')
        texto.name = 'x.txt'
        self.assertEqual(self.api.post(f'{url}/adjuntos/', {'archivo': texto}, format='multipart').status_code, 400)
        b = nueva_institucion('JUNTA-B')
        admin_de(b)
        otra = cliente_de(b)
        self.assertEqual(otra.get(f'{url}/').status_code, 404)
        self.assertEqual(otra.get(f'{url}/adjuntos/{codigo}/').status_code, 404)
        usuario_con_permisos(self.a, 'consulta', ['gastos.consultar'])
        consulta = cliente_de(self.a, 'consulta')
        self.assertEqual(consulta.get(f'{url}/adjuntos/{codigo}/').status_code, 200)
        self.assertEqual(consulta.post('/api/v1/gastos/', {}, format='json').status_code, 403)


class RevisionTests(BaseCaja):
    def test_declaraciones_invalidas(self):
        ref = self.sesion()['referencia']
        url = f'/api/v1/sesiones-caja/{ref}/cerrar/'
        for cuerpo in ({'declarados': {'EFECTIVO': 1}}, {'declarados': 'x'}, {'declarados': [{'forma_pago': 5}]},
                       {'declarados': [{'forma_pago': 'EFECTIVO', 'importe': 1}, {'forma_pago': 'efectivo', 'importe': 2}]}):
            self.assertEqual(self.api.post(url, cuerpo, format='json').status_code, 400, cuerpo)
        self.assertEqual(self.cerrar(ref, {'EFECTIVO': 100000, 'TRANSFERENCIA': 5000}, 'x', codigo=400)['codigo'],
                         'forma_sin_movimientos')
        self.assertEqual(self.cerrar(ref, {'EFECTIVO': 100000, 'TRANSFERENCIA': 0})['estado'], 'cerrada')

    def test_el_arqueo_de_una_sesion_cerrada_no_cambia_si_se_reordenan_las_formas(self):
        ref = self.sesion()['referencia']
        self.cerrar(ref, {'EFECTIVO': 100000})
        self.api.post('/api/v1/formas-pago/', {'Code': 'EFE2', 'nombre': 'Efectivo 2', 'tipo': 'efectivo', 'orden': 0},
                      format='json')
        self.api.patch('/api/v1/formas-pago/EFECTIVO/', {'activa': False}, format='json')
        datos = self.api.get(f'/api/v1/sesiones-caja/{ref}/').data
        self.assertEqual([(f['forma_pago'], D(f['esperado'])) for f in datos['resumen']], [('EFECTIVO', D('100000'))])

    def test_reversion_automatica_despues_del_cierre_queda_a_la_vista(self):
        from apps.auditoria.models import RegistroAuditoria
        from apps.caja import servicios
        from apps.cobranzas.models import Pago
        self.emitir([self.oct])
        ref = self.sesion()['referencia']
        self.cerrar(ref, {'EFECTIVO': 144000}, 'faltan 800')
        self.api.post(f'/api/v1/sesiones-caja/{ref}/revisar/', {'comentario': 'descontado'}, format='json')
        servicios.revertir_cobro(Pago.objects.get(), usuario=None)        # ej. rechazo del proveedor electrónico
        sesion = SesionCaja.objects.get(referencia=ref)
        self.assertEqual((sesion.estado, sesion.revisada_por), ('en_revision', None))
        self.assertTrue(RegistroAuditoria.objects.filter(accion='caja_reabierta_a_revision', entidad_id=ref).exists())
        self.api.post(f'/api/v1/sesiones-caja/{ref}/revisar/', {'comentario': 'ok2'}, format='json')
        historial = SesionCaja.objects.get(referencia=ref).comentario_revision
        self.assertIn('descontado', historial)
        self.assertIn('Reversión automática', historial)
        self.assertIn('ok2', historial)
        pdf = self.api.get(f'/api/v1/sesiones-caja/{ref}/pdf/')
        self.assertEqual(pdf.status_code, 200)

    def test_anular_un_gasto_de_una_caja_cerrada(self):
        g = self.gasto()
        url = f'/api/v1/gastos/{g["referencia"]}'
        self.api.post(f'{url}/confirmar/')
        primera = self.sesion()['referencia']
        self.cerrar(primera, {'EFECTIVO': 85000})
        self.assertEqual(self.api.post(f'{url}/anular/', {'motivo': 'x'}, format='json').data['codigo'], 'caja_cerrada')
        self.api.post('/api/v1/caja/mi-sesion/', {'caja': 'CAJA1', 'saldo_inicial': '0'}, format='json')
        self.assertEqual(self.api.post(f'{url}/anular/', {'motivo': 'x'}, format='json').status_code, 200)
        self.assertEqual(self.resumen()['EFECTIVO'], (D('15000'), D('0'), D('15000')))
        self.assertEqual(SesionCaja.objects.get(referencia=primera).estado, 'cerrada')
