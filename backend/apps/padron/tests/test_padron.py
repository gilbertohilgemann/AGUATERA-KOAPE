"""
Pruebas de la Fase 2: padrón, territorio, medidores, fotos privadas y mapa.

Cubre las pruebas obligatorias de la sección 21 que corresponden a esta fase:
1 (aislamiento), 5 (el historial conserva el medidor correcto tras una sustitución),
17 (archivados siguen disponibles), 18 (sin borrado físico) y 20 (archivos privados).
"""
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auditoria.models import RegistroAuditoria
from apps.padron.models import Cliente, Conexion, InstalacionMedidor, Medidor
from apps.territorio.models import Barrio, Zona
from comun.pruebas.utilidades import LimpiarLimites, admin_de, cliente_de, nueva_institucion, usuario_con_permisos

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64
POLIGONO = {'type': 'Polygon', 'coordinates': [[[-57.60, -25.30], [-57.50, -25.30], [-57.50, -25.20],
                                                [-57.60, -25.20], [-57.60, -25.30]]]}


class BasePadron(LimpiarLimites, TestCase):
    def setUp(self):
        super().setUp()
        self._privado = tempfile.mkdtemp()
        self._ajustes = override_settings(DIR_PRIVADO=Path(self._privado))
        self._ajustes.enable()
        self.a = nueva_institucion('JUNTA-A')
        self.b = nueva_institucion('JUNTA-B')
        admin_de(self.a)
        admin_de(self.b)
        self.api = cliente_de(self.a)
        self.api_b = cliente_de(self.b)

    def tearDown(self):
        self._ajustes.disable()
        shutil.rmtree(self._privado, ignore_errors=True)
        super().tearDown()

    _siguiente = 0

    def crear(self, api, ruta, datos, codigo=201):
        if 'Code' not in datos:
            # El Code lo carga siempre el usuario: en las pruebas se le da uno si el caso no lo fija.
            BasePadron._siguiente += 1
            datos = {**datos, 'Code': f'T-{BasePadron._siguiente}'}
        r = api.post(f'/api/v1/{ruta}', datos, format='json')
        self.assertEqual(r.status_code, codigo, r.data)
        return r.data

    def armar_basico(self, api, prefijo=''):
        zona = self.crear(api, 'zonas/', {'Code': f'{prefijo}z1', 'nombre': 'Centro', 'color': '#1D4ED8',
                                          'poligono': POLIGONO})
        barrio = self.crear(api, 'barrios/', {'zona': zona['Code'], 'Code': f'{prefijo}b1', 'nombre': 'San Roque'})
        cliente = self.crear(api, 'clientes/', {'Code': f'{prefijo}C1', 'nombre': 'María Benítez', 'documento': '1234567'})
        conexion = self.crear(api, 'conexiones/', {'Code': f'{prefijo}CX1', 'cliente': cliente['Code'],
                                                   'barrio': barrio['Code'], 'direccion': 'Calle 1',
                                                   'latitud': '-25.250000', 'longitud': '-57.550000'})
        medidor = self.crear(api, 'medidores/', {'Code': f'{prefijo}m-001', 'marca': 'Elster', 'lectura_maxima': '99999'})
        return zona, barrio, cliente, conexion, medidor


class AislamientoPadronTests(BasePadron):
    def test_cada_institucion_ve_solo_su_padron(self):
        _, barrio_b, cliente_b, conexion_b, medidor_b = self.armar_basico(self.api_b, 'B')
        self.armar_basico(self.api)
        for ruta in ('clientes/', 'conexiones/', 'medidores/'):
            ids = {x['Code'] for x in self.api.get(f'/api/v1/{ruta}').data['results']}
            self.assertEqual(len(ids), 1, ruta)
        self.assertEqual(self.api.get(f'/api/v1/clientes/{cliente_b["Code"]}/').status_code, 404)
        self.assertEqual(self.api.get(f'/api/v1/conexiones/{conexion_b["Code"]}/').status_code, 404)
        self.assertEqual(self.api.get(f'/api/v1/medidores/{medidor_b["Code"]}/').status_code, 404)
        self.assertEqual(self.api.get(f'/api/v1/barrios/{barrio_b["Code"]}/').status_code, 404)
        mapa = self.api.get('/api/v1/mapa/').data
        self.assertEqual(len(mapa['conexiones']), 1)
        self.assertNotIn(conexion_b['Code'], {c['Code'] for c in mapa['conexiones']})

    def test_no_se_relacionan_registros_de_otra_institucion(self):
        zona_b, barrio_b, cliente_b, _, medidor_b = self.armar_basico(self.api_b, 'B')
        _, barrio, cliente, conexion, _ = self.armar_basico(self.api)
        r = self.api.post('/api/v1/conexiones/', {'Code': 'N1', 'cliente': cliente_b['Code']}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.api.post('/api/v1/conexiones/', {'Code': 'N1', 'cliente': cliente['Code'], 'barrio': barrio_b['Code']}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.api.post('/api/v1/barrios/', {'zona': zona_b['Code'], 'Code': 'X', 'nombre': 'X'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.api.post(f'/api/v1/conexiones/{conexion["Code"]}/instalar-medidor/',
                          {'medidor': medidor_b['Code'], 'fecha': '2026-10-01', 'lectura_inicial': '0'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.api.post(f'/api/v1/conexiones/{conexion["Code"]}/titular/',
                          {'cliente': cliente_b['Code'], 'desde': '2026-10-01', 'motivo': 'x'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(InstalacionMedidor.objects.exists())

    def test_los_codigos_se_repiten_entre_instituciones_pero_no_dentro(self):
        self.crear(self.api, 'clientes/', {'Code': 'X1', 'nombre': 'Uno'})
        self.crear(self.api_b, 'clientes/', {'Code': 'X1', 'nombre': 'Uno en B'})
        self.crear(self.api, 'clientes/', {'Code': 'x1', 'nombre': 'Repetido'}, codigo=400)


class ClientesTests(BasePadron):
    def test_code_lo_carga_el_usuario_y_no_se_cambia(self):
        # Sin Code no hay alta: el sistema no lo inventa.
        r = self.api.post('/api/v1/clientes/', {'nombre': 'Sin código'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('Code', r.data['campos'] if 'campos' in r.data else r.data)
        for malo in ('', 'con espacio', 'ÑANDU', '-X', 'A/B'):
            self.crear(self.api, 'clientes/', {'Code': malo, 'nombre': 'X'}, codigo=400)
        cliente = self.crear(self.api, 'clientes/', {'Code': ' cli-01 ', 'nombre': 'Uno'})
        self.assertEqual(cliente['Code'], 'CLI-01')  # se guarda en mayúsculas
        # Se busca por Code (también en minúsculas) y no se cambia después.
        self.assertEqual(self.api.get('/api/v1/clientes/cli-01/').data['nombre'], 'Uno')
        r = self.api.patch('/api/v1/clientes/CLI-01/', {'Code': 'OTRO'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.api.patch('/api/v1/clientes/CLI-01/', {'Code': 'CLI-01', 'telefono': '0981'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(RegistroAuditoria.objects.filter(accion='cliente_creado').get().entidad_id, 'CLI-01')
        # Tampoco por el servicio ni en la conexión (un Code distinto responde 400, el mismo se acepta).
        from apps.padron import servicios
        from comun.errores import ErrorNegocio
        with self.assertRaises(ErrorNegocio):
            servicios.actualizar_cliente(Cliente.objects.get(Code='CLI-01'), {'Code': 'OTRO CODE'})
        conexion = self.crear(self.api, 'conexiones/', {'Code': 'CX-9', 'cliente': 'CLI-01'})
        self.assertEqual(self.api.patch(f'/api/v1/conexiones/{conexion["Code"]}/', {'Code': 'CX-10'},
                                        format='json').status_code, 400)
        self.assertEqual(self.api.patch('/api/v1/conexiones/cx-9/', {'Code': 'cx-9', 'direccion': 'X'},
                                        format='json').status_code, 200)

    def test_un_cliente_puede_tener_varias_conexiones(self):
        cliente = self.crear(self.api, 'clientes/', {'nombre': 'Juan'})
        self.crear(self.api, 'conexiones/', {'cliente': cliente['Code'], 'direccion': 'Casa'})
        self.crear(self.api, 'conexiones/', {'cliente': cliente['Code'], 'direccion': 'Local'})
        self.assertEqual(len(self.api.get(f'/api/v1/clientes/{cliente["Code"]}/conexiones/').data), 2)
        self.assertEqual(self.api.get(f'/api/v1/clientes/{cliente["Code"]}/').data['cantidad_conexiones'], 2)

    def test_archivar_cliente_con_conexiones_vigentes_se_rechaza_y_archivados_siguen_visibles(self):
        _, _, cliente, conexion, _ = self.armar_basico(self.api)
        r = self.api.patch(f'/api/v1/clientes/{cliente["Code"]}/', {'estado': 'archivado'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.api.post(f'/api/v1/conexiones/{conexion["Code"]}/estado/', {'estado': 'archivada', 'motivo': 'Baja'},
                      format='json')
        r = self.api.patch(f'/api/v1/clientes/{cliente["Code"]}/', {'estado': 'archivado'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.api.get('/api/v1/clientes/').data['count'], 0)
        self.assertEqual(self.api.get('/api/v1/clientes/?incluir_archivados=1').data['count'], 1)
        self.assertEqual(self.api.get(f'/api/v1/clientes/{cliente["Code"]}/').status_code, 200)
        self.assertEqual(self.api.get('/api/v1/conexiones/?incluir_archivadas=1').data['count'], 1)
        # Un cliente archivado no recibe conexiones nuevas.
        self.crear(self.api, 'conexiones/', {'cliente': cliente['Code']}, codigo=400)
        self.assertTrue(RegistroAuditoria.objects.filter(accion='cliente_archivado').exists())

    def test_no_hay_borrado_fisico(self):
        zona, barrio, cliente, conexion, medidor = self.armar_basico(self.api)
        for ruta in (f'clientes/{cliente["Code"]}/', f'conexiones/{conexion["Code"]}/', f'medidores/{medidor["Code"]}/',
                     f'zonas/{zona["Code"]}/', f'barrios/{barrio["Code"]}/'):
            self.assertEqual(self.api.delete(f'/api/v1/{ruta}').status_code, 405, ruta)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cliente.objects.get(institucion=self.a, Code=cliente['Code']).delete()  # PROTECT: tiene conexiones


class ConexionesTests(BasePadron):
    def test_transiciones_de_estado(self):
        _, _, _, conexion, _ = self.armar_basico(self.api)
        url = f'/api/v1/conexiones/{conexion["Code"]}/estado/'
        self.assertEqual(self.api.post(url, {'estado': 'activa', 'motivo': ''}, format='json').status_code, 400)
        self.assertEqual(self.api.post(url, {'estado': 'suspendida', 'motivo': 'x'}, format='json').status_code, 400)
        r = self.api.post(url, {'estado': 'activa', 'motivo': 'Instalación terminada'}, format='json')
        self.assertEqual(r.data['estado'], 'activa')
        self.assertIn('suspendida', {t['estado'] for t in r.data['transiciones']})
        self.api.post(url, {'estado': 'suspendida', 'motivo': 'Pedido del usuario'}, format='json')
        registro = RegistroAuditoria.objects.filter(accion='conexion_estado').order_by('id').last()
        self.assertEqual((registro.antes, registro.despues, registro.motivo),
                         ({'estado': 'activa'}, {'estado': 'suspendida'}, 'Pedido del usuario'))

    def test_pendiente_de_ubicacion_no_se_activa_sin_coordenadas(self):
        cliente = self.crear(self.api, 'clientes/', {'nombre': 'Sin GPS'})
        conexion = self.crear(self.api, 'conexiones/', {'cliente': cliente['Code'], 'estado': 'pendiente_ubicacion'})
        url = f'/api/v1/conexiones/{conexion["Code"]}/estado/'
        self.assertEqual(self.api.post(url, {'estado': 'activa', 'motivo': 'x'}, format='json').status_code, 400)
        r = self.api.patch(f'/api/v1/conexiones/{conexion["Code"]}/', {'latitud': '-25.3', 'longitud': '-57.6',
                                                                     'metodo_ubicacion': 'gps', 'precision_metros': 8},
                           format='json')
        self.assertEqual(r.data['metodo_ubicacion'], 'gps')
        self.assertEqual(self.api.post(url, {'estado': 'activa', 'motivo': 'x'}, format='json').status_code, 200)

    def test_validacion_de_coordenadas(self):
        cliente = self.crear(self.api, 'clientes/', {'nombre': 'Coordenadas'})
        self.crear(self.api, 'conexiones/', {'cliente': cliente['Code'], 'latitud': '-25.3'}, codigo=400)
        r = self.api.post('/api/v1/conexiones/', {'Code': 'INV', 'cliente': cliente['Code'], 'latitud': '-57.6',
                                                  'longitud': '-25.3'},
                          format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('invertidas', r.data['detalle'])
        conexion = self.crear(self.api, 'conexiones/', {'cliente': cliente['Code'], 'latitud': '-25.3', 'longitud': '-57.6'})
        self.assertEqual(conexion['metodo_ubicacion'], 'manual')
        r = self.api.patch(f'/api/v1/conexiones/{conexion["Code"]}/', {'latitud': None, 'longitud': None}, format='json')
        self.assertEqual(r.data['metodo_ubicacion'], 'sin_ubicacion')

    def test_el_estado_y_el_titular_no_se_cambian_por_edicion_comun(self):
        _, _, _, conexion, _ = self.armar_basico(self.api)
        r = self.api.patch(f'/api/v1/conexiones/{conexion["Code"]}/', {'estado': 'activa', 'direccion': 'Nueva'},
                           format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.data['estado'], r.data['direccion']), ('en_instalacion', 'Nueva'))

    def test_cambio_de_titular_con_historial(self):
        _, _, cliente, conexion, _ = self.armar_basico(self.api)
        nuevo = self.crear(self.api, 'clientes/', {'nombre': 'Nuevo dueño'})
        url = f'/api/v1/conexiones/{conexion["Code"]}/titular/'
        self.assertEqual(self.api.post(url, {'cliente': nuevo['Code'], 'desde': '2020-01-01', 'motivo': 'x'},
                                       format='json').status_code, 400)  # anterior al titular actual
        r = self.api.post(url, {'cliente': nuevo['Code'], 'desde': str(timezone.localdate()), 'motivo': 'Venta de la casa'},
                          format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['cliente'], nuevo['Code'])
        historial = r.data['titularidades']
        self.assertEqual([(t['cliente'], t['hasta']) for t in historial],
                         [(nuevo['Code'], None), (cliente['Code'], str(timezone.localdate()))])

    def test_filtros(self):
        _, barrio, cliente, conexion, _ = self.armar_basico(self.api)
        self.crear(self.api, 'conexiones/', {'cliente': cliente['Code'], 'direccion': 'Sin ubicar'})
        r = self.api.get('/api/v1/conexiones/?ubicacion=sin')
        self.assertEqual([c['direccion'] for c in r.data['results']], ['Sin ubicar'])
        self.assertEqual(self.api.get(f'/api/v1/conexiones/?barrio={barrio["Code"]}').data['count'], 1)
        self.assertEqual(self.api.get('/api/v1/conexiones/?buscar=benítez').data['count'], 2)
        self.assertEqual(self.api.get('/api/v1/conexiones/?sin_medidor=1').data['count'], 2)
        mapa = self.api.get('/api/v1/mapa/').data
        self.assertEqual((len(mapa['conexiones']), mapa['sin_ubicacion'], mapa['total']), (1, 1, 2))
        self.assertEqual(mapa['zonas'][0]['poligono']['type'], 'Polygon')


class MedidoresTests(BasePadron):
    def test_sustitucion_conserva_el_historial(self):
        _, _, _, conexion, medidor = self.armar_basico(self.api)
        base = f'/api/v1/conexiones/{conexion["Code"]}'
        r = self.api.post(f'{base}/instalar-medidor/', {'medidor': medidor['Code'], 'fecha': '2026-01-10',
                                                        'lectura_inicial': '15.5'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['medidor_actual'], 'M-001')
        primera = InstalacionMedidor.objects.get()
        nuevo = self.crear(self.api, 'medidores/', {'Code': 'M-002'})
        r = self.api.post(f'{base}/instalar-medidor/', {'medidor': nuevo['Code'], 'fecha': '2026-02-01',
                                                        'lectura_inicial': '0'}, format='json')
        self.assertEqual(r.data['codigo'], 'ya_tiene_medidor')
        r = self.api.post(f'{base}/sustituir-medidor/', {'medidor': nuevo['Code'], 'fecha': '2026-06-01',
                                                         'lectura_retiro': '120.25', 'lectura_inicial': '0',
                                                         'motivo': 'Medidor trabado', 'estado_medidor_retirado': 'danado'},
                          format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['medidor_actual'], 'M-002')
        primera.refresh_from_db()
        # La instalación vieja (a la que apuntarán las lecturas históricas) conserva su medidor y su cierre.
        self.assertEqual((primera.medidor.Code, str(primera.lectura_retiro), str(primera.fecha_retiro)),
                         ('M-001', '120.250', '2026-06-01'))
        self.assertEqual(Medidor.objects.get(Code='M-001').estado, 'danado')
        self.assertEqual(Medidor.objects.get(Code='M-002').estado, 'instalado')
        self.assertEqual([i['medidor'] for i in r.data['instalaciones']], ['M-002', 'M-001'])
        historial = self.api.get(f'/api/v1/medidores/{medidor["Code"]}/historial/').data
        self.assertEqual(historial[0]['conexion'], conexion['Code'])
        self.assertTrue(RegistroAuditoria.objects.filter(accion='medidor_sustituido', motivo='Medidor trabado').exists())

    def test_un_medidor_no_se_instala_en_dos_conexiones(self):
        _, _, cliente, conexion, medidor = self.armar_basico(self.api)
        otra = self.crear(self.api, 'conexiones/', {'cliente': cliente['Code']})
        datos = {'medidor': medidor['Code'], 'fecha': '2026-01-10', 'lectura_inicial': '0'}
        self.assertEqual(self.api.post(f'/api/v1/conexiones/{conexion["Code"]}/instalar-medidor/', datos,
                                       format='json').status_code, 200)
        self.assertEqual(self.api.post(f'/api/v1/conexiones/{otra["Code"]}/instalar-medidor/', datos,
                                       format='json').status_code, 400)
        # Y la base lo impide aunque alguien se saltee el servicio.
        with self.assertRaises(IntegrityError), transaction.atomic():
            InstalacionMedidor.objects.create(institucion=self.a, conexion=Conexion.objects.get(Code=otra['Code']),
                                              medidor=Medidor.objects.get(Code=medidor['Code']),
                                              fecha_instalacion='2026-02-01', lectura_inicial=Decimal('0'))

    def test_retiro_con_lectura_menor_exige_confirmacion(self):
        _, _, _, conexion, medidor = self.armar_basico(self.api)
        base = f'/api/v1/conexiones/{conexion["Code"]}'
        self.api.post(f'{base}/instalar-medidor/', {'medidor': medidor['Code'], 'fecha': '2026-01-10',
                                                    'lectura_inicial': '500'}, format='json')
        datos = {'fecha': '2026-03-01', 'lectura_retiro': '20', 'motivo': 'Contador volvió a cero'}
        r = self.api.post(f'{base}/retirar-medidor/', datos, format='json')
        self.assertEqual(r.data['codigo'], 'lectura_menor')
        r = self.api.post(f'{base}/retirar-medidor/', {**datos, 'aceptar_lectura_menor': True}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.data['medidor_actual'])
        self.assertEqual(Medidor.objects.get(institucion=self.a, Code=medidor['Code']).estado, 'retirado')
        r = self.api.post(f'{base}/retirar-medidor/', datos, format='json')
        self.assertEqual(r.status_code, 400)

    def test_retiro_anterior_a_la_instalacion_se_rechaza(self):
        _, _, _, conexion, medidor = self.armar_basico(self.api)
        base = f'/api/v1/conexiones/{conexion["Code"]}'
        self.api.post(f'{base}/instalar-medidor/', {'medidor': medidor['Code'], 'fecha': '2026-05-10',
                                                    'lectura_inicial': '0'}, format='json')
        r = self.api.post(f'{base}/retirar-medidor/', {'fecha': '2026-05-01', 'lectura_retiro': '1', 'motivo': 'x'},
                          format='json')
        self.assertEqual(r.status_code, 400)

    def test_estado_de_un_medidor_instalado_no_se_cambia_a_mano(self):
        _, _, _, conexion, medidor = self.armar_basico(self.api)
        self.api.post(f'/api/v1/conexiones/{conexion["Code"]}/instalar-medidor/',
                      {'medidor': medidor['Code'], 'fecha': '2026-01-10', 'lectura_inicial': '0'}, format='json')
        r = self.api.patch(f'/api/v1/medidores/{medidor["Code"]}/', {'estado': 'baja'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.api.patch(f'/api/v1/medidores/{medidor["Code"]}/', {'Code': 'OTRO'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.api.patch(f'/api/v1/medidores/{medidor["Code"]}/', {'marca': 'Itron'}, format='json')
        self.assertEqual(r.status_code, 200)

    def test_numero_del_medidor_alfanumerico_unico_y_buscable(self):
        _, _, _, conexion, medidor = self.armar_basico(self.api)
        r = self.api.patch(f'/api/v1/medidores/{medidor["Code"]}/', {'numero': ' ab-1234x '}, format='json')
        self.assertEqual((r.status_code, r.data['numero']), (200, 'AB-1234X'))
        self.assertEqual(self.api.patch(f'/api/v1/medidores/{medidor["Code"]}/', {'numero': 'con espacio'},
                                        format='json').status_code, 400)
        r = self.api.post('/api/v1/medidores/', {'Code': 'M-777', 'numero': 'ab-1234X'}, format='json')
        self.assertEqual((r.status_code, r.data.get('codigo')), (400, 'numero_repetido'))
        # Tampoco puede ser el código de otro medidor (ni un código nuevo, el número de otro): el cobrador escribe
        # uno u otro para identificarlo.
        self.assertEqual(self.api.post('/api/v1/medidores/', {'Code': 'M-780', 'numero': medidor['Code']},
                                       format='json').data.get('codigo'), 'numero_repetido')
        self.assertEqual(self.api.post('/api/v1/medidores/', {'Code': 'AB-1234X'}, format='json').status_code, 400)
        # Sin número no choca (varios medidores pueden no tenerlo cargado).
        self.assertEqual(self.api.post('/api/v1/medidores/', {'Code': 'M-778'}, format='json').status_code, 201)
        self.assertEqual(self.api.post('/api/v1/medidores/', {'Code': 'M-779'}, format='json').status_code, 201)
        self.assertEqual([m['Code'] for m in self.api.get('/api/v1/medidores/?buscar=1234x').data['results']],
                         [medidor['Code']])
        self.api.post(f'/api/v1/conexiones/{conexion["Code"]}/instalar-medidor/',
                      {'medidor': medidor['Code'], 'fecha': '2026-01-10', 'lectura_inicial': '0'}, format='json')
        filas = self.api.get('/api/v1/conexiones/?buscar=AB-1234').data['results']
        self.assertEqual([(c['Code'], c['medidor_numero']) for c in filas], [(conexion['Code'], 'AB-1234X')])

    def test_conexion_archivada_no_recibe_medidor(self):
        _, _, _, conexion, medidor = self.armar_basico(self.api)
        self.api.post(f'/api/v1/conexiones/{conexion["Code"]}/estado/', {'estado': 'archivada', 'motivo': 'x'},
                      format='json')
        r = self.api.post(f'/api/v1/conexiones/{conexion["Code"]}/instalar-medidor/',
                          {'medidor': medidor['Code'], 'fecha': '2026-01-10', 'lectura_inicial': '0'}, format='json')
        self.assertEqual(r.status_code, 400)


class TerritorioTests(BasePadron):
    def test_poligono_valido_y_archivado(self):
        self.crear(self.api, 'zonas/', {'Code': 'Z', 'nombre': 'Mala', 'poligono': {'type': 'Point',
                                                                                      'coordinates': [1, 2]}}, codigo=400)
        abierto = {'type': 'Polygon', 'coordinates': [[[-57.6, -25.3], [-57.5, -25.3], [-57.5, -25.2]]]}
        self.crear(self.api, 'zonas/', {'Code': 'Z', 'nombre': 'Abierta', 'poligono': abierto}, codigo=400)
        zona = self.crear(self.api, 'zonas/', {'Code': 'Z', 'nombre': 'Norte', 'poligono': POLIGONO})
        self.api.patch(f'/api/v1/zonas/{zona["Code"]}/', {'activa': False}, format='json')
        self.assertTrue(RegistroAuditoria.objects.filter(accion='zona_archivado').exists())
        self.crear(self.api, 'barrios/', {'zona': zona['Code'], 'Code': 'B', 'nombre': 'B'}, codigo=400)
        self.assertEqual(len(self.api.get('/api/v1/zonas/').data), 1)
        self.assertEqual(len(self.api.get('/api/v1/zonas/?activos=1').data), 0)

    def test_barrio_archivado_no_se_asigna_a_conexiones_nuevas(self):
        _, barrio, cliente, conexion, _ = self.armar_basico(self.api)
        self.api.patch(f'/api/v1/barrios/{barrio["Code"]}/', {'activo': False}, format='json')
        self.crear(self.api, 'conexiones/', {'cliente': cliente['Code'], 'barrio': barrio['Code']}, codigo=400)
        # La conexión que ya estaba en ese barrio lo conserva y se puede seguir editando.
        r = self.api.patch(f'/api/v1/conexiones/{conexion["Code"]}/', {'direccion': 'Otra', 'barrio': barrio['Code']},
                           format='json')
        self.assertEqual(r.status_code, 200)

    def test_punto_en_poligono(self):
        from comun.geo import punto_en_poligono
        self.assertTrue(punto_en_poligono(-25.25, -57.55, POLIGONO))
        self.assertFalse(punto_en_poligono(-25.10, -57.55, POLIGONO))


class FotosPrivadasTests(BasePadron):
    def test_foto_de_vivienda_privada(self):
        _, _, _, conexion, _ = self.armar_basico(self.api)
        url = f'/api/v1/conexiones/{conexion["Code"]}/foto-vivienda/'
        texto = SimpleUploadedFile('casa.png', b'no soy una imagen', content_type='image/png')
        self.assertEqual(self.api.post(url, {'archivo': texto}, format='multipart').status_code, 400)
        foto = SimpleUploadedFile('casa.png', PNG, content_type='image/png')
        r = self.api.post(url, {'archivo': foto}, format='multipart')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data['tiene_foto_vivienda'])
        guardada = Conexion.objects.get(institucion=self.a, Code=conexion['Code']).foto_vivienda
        self.assertNotIn('casa', guardada)  # nombre aleatorio
        self.assertTrue((Path(settings.DIR_PRIVADO) / guardada).is_file())
        self.assertFalse(str(Path(settings.DIR_PRIVADO)).startswith(str(settings.MEDIA_ROOT)))
        r = self.api.get(url)
        self.assertEqual((r.status_code, r['Content-Type']), (200, 'image/png'))
        self.assertEqual(b''.join(r.streaming_content), PNG)
        self.assertEqual(self.api_b.get(url).status_code, 404)        # otra institución
        self.assertEqual(APIClient().get(url).status_code, 401)        # sin sesión
        usuario_con_permisos(self.a, 'sin_padron', ['institucion.ver'])
        self.assertEqual(cliente_de(self.a, 'sin_padron').get(url).status_code, 403)  # sin permiso

    def test_no_se_sirve_un_archivo_de_otra_institucion_aunque_se_conozca_la_ruta(self):
        from django.http import Http404

        from comun import archivos_privados
        _, _, _, conexion, _ = self.armar_basico(self.api)
        self.api.post(f'/api/v1/conexiones/{conexion["Code"]}/foto-vivienda/',
                      {'archivo': SimpleUploadedFile('c.png', PNG)}, format='multipart')
        ruta = Conexion.objects.get(institucion=self.a, Code=conexion['Code']).foto_vivienda
        with self.assertRaises(Http404):
            archivos_privados.ruta_absoluta(self.b, ruta)
        with self.assertRaises(Http404):
            archivos_privados.ruta_absoluta(self.a, '../../etc/passwd')


class PermisosPadronTests(BasePadron):
    def test_consulta_sin_edicion_y_mapa_con_su_permiso(self):
        self.armar_basico(self.api)
        usuario_con_permisos(self.a, 'consulta', ['padron.consultar'])
        cliente = cliente_de(self.a, 'consulta')
        self.assertEqual(cliente.get('/api/v1/conexiones/').status_code, 200)
        self.assertEqual(cliente.get('/api/v1/zonas/').status_code, 200)
        self.assertEqual(cliente.post('/api/v1/clientes/', {'nombre': 'X'}, format='json').status_code, 403)
        self.assertEqual(cliente.get('/api/v1/mapa/').status_code, 403)

    def test_instalar_medidor_pide_su_permiso(self):
        _, _, _, conexion, medidor = self.armar_basico(self.api)
        usuario_con_permisos(self.a, 'conexiones', ['padron.conexiones', 'padron.consultar'])
        cliente = cliente_de(self.a, 'conexiones')
        r = cliente.post(f'/api/v1/conexiones/{conexion["Code"]}/instalar-medidor/',
                         {'medidor': medidor['Code'], 'fecha': '2026-01-10', 'lectura_inicial': '0'}, format='json')
        self.assertEqual(r.status_code, 403)
        r = cliente.patch(f'/api/v1/conexiones/{conexion["Code"]}/', {'direccion': 'X'}, format='json')
        self.assertEqual(r.status_code, 200)

    def test_resumen(self):
        self.armar_basico(self.api)
        r = self.api.get('/api/v1/padron/resumen/').data
        self.assertEqual((r['clientes'], r['conexiones'], r['sin_medidor'], r['medidores_disponibles']), (1, 1, 1, 1))
        self.assertEqual(Zona.objects.count() + Barrio.objects.count(), 2)


class RevisionPadronTests(BasePadron):
    """Casos que encontró la revisión independiente de la Fase 2."""

    def test_el_id_interno_nunca_se_expone(self):
        zona, barrio, cliente, conexion, medidor = self.armar_basico(self.api)
        base = f'/api/v1/conexiones/{conexion["Code"]}'
        self.api.post(f'{base}/instalar-medidor/', {'medidor': medidor['Code'], 'fecha': '2026-01-01',
                                                    'lectura_inicial': '0'}, format='json')

        def sin_id(dato, ruta):
            if isinstance(dato, dict):
                self.assertNotIn('id', dato, ruta)
                for v in dato.values():
                    sin_id(v, ruta)
            elif isinstance(dato, list):
                for v in dato:
                    sin_id(v, ruta)

        for ruta in ('clientes/', 'conexiones/', 'medidores/', 'zonas/', 'barrios/', 'mapa/',
                     f'clientes/{cliente["Code"]}/', f'clientes/{cliente["Code"]}/conexiones/',
                     f'conexiones/{conexion["Code"]}/', f'medidores/{medidor["Code"]}/',
                     f'medidores/{medidor["Code"]}/historial/', f'zonas/{zona["Code"]}/', f'barrios/{barrio["Code"]}/'):
            r = self.api.get(f'/api/v1/{ruta}')
            self.assertEqual(r.status_code, 200, ruta)
            sin_id(r.data, ruta)
        # Las referencias van por Code: conexión → cliente, barrio, zona; barrio → zona.
        detalle = self.api.get(f'{base}/').data
        self.assertEqual((detalle['cliente'], detalle['barrio'], detalle['zona']),
                         (cliente['Code'], barrio['Code'], zona['Code']))
        self.assertEqual(barrio['zona'], zona['Code'])
        # Un id numérico en la ruta no encuentra nada.
        pk = Conexion.objects.get(Code=conexion['Code']).pk
        self.assertEqual(self.api.get(f'/api/v1/conexiones/{pk}/').status_code, 404)

    def test_los_periodos_de_medidores_de_una_conexion_no_se_superponen(self):
        _, _, _, conexion, m1 = self.armar_basico(self.api)
        m2 = self.crear(self.api, 'medidores/', {'Code': 'M-2'})
        base = f'/api/v1/conexiones/{conexion["Code"]}'
        self.api.post(f'{base}/instalar-medidor/', {'medidor': m1['Code'], 'fecha': '2026-01-01', 'lectura_inicial': '0'}, format='json')
        self.api.post(f'{base}/retirar-medidor/', {'fecha': '2026-06-01', 'lectura_retiro': '50', 'motivo': 'x'}, format='json')
        r = self.api.post(f'{base}/instalar-medidor/', {'medidor': m2['Code'], 'fecha': '2026-02-01', 'lectura_inicial': '0'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.api.post(f'{base}/instalar-medidor/', {'medidor': m2['Code'], 'fecha': '2026-06-01', 'lectura_inicial': '0'}, format='json')
        self.assertEqual(r.status_code, 200)

    def test_parametros_desconocidos_no_rompen(self):
        self.armar_basico(self.api)
        for url in ('conexiones/?zona=abc', 'conexiones/?barrio=1.5', 'conexiones/?cliente=x', 'mapa/?zona=abc',
                    'barrios/?zona=abc', 'conexiones/?zona=%27%3B--'):
            r = self.api.get(f'/api/v1/{url}')
            self.assertEqual(r.status_code, 200, url)

    def test_archivar_exige_retirar_el_medidor_y_restaurar_exige_titular_vigente(self):
        _, _, cliente, conexion, medidor = self.armar_basico(self.api)
        base = f'/api/v1/conexiones/{conexion["Code"]}'
        self.api.post(f'{base}/instalar-medidor/', {'medidor': medidor['Code'], 'fecha': '2026-01-01', 'lectura_inicial': '0'}, format='json')
        r = self.api.post(f'{base}/estado/', {'estado': 'archivada', 'motivo': 'x'}, format='json')
        self.assertEqual(r.data['codigo'], 'tiene_medidor')
        self.api.post(f'{base}/retirar-medidor/', {'fecha': '2026-02-01', 'lectura_retiro': '1', 'motivo': 'baja'}, format='json')
        self.assertEqual(self.api.post(f'{base}/estado/', {'estado': 'archivada', 'motivo': 'x'}, format='json').status_code, 200)
        self.api.patch(f'/api/v1/clientes/{cliente["Code"]}/', {'estado': 'archivado'}, format='json')
        self.assertEqual(self.api.post(f'{base}/estado/', {'estado': 'desconectada', 'motivo': 'x'}, format='json').status_code, 400)
        self.assertEqual(self.api.post(f'{base}/foto-vivienda/', {'archivo': SimpleUploadedFile('c.png', PNG)},
                                       format='multipart').status_code, 400)

    def test_activa_exige_ubicacion_siempre(self):
        cliente = self.crear(self.api, 'clientes/', {'nombre': 'X'})
        self.crear(self.api, 'conexiones/', {'cliente': cliente['Code'], 'estado': 'activa'}, codigo=400)
        conexion = self.crear(self.api, 'conexiones/', {'cliente': cliente['Code']})
        url = f'/api/v1/conexiones/{conexion["Code"]}'
        self.assertEqual(self.api.post(f'{url}/estado/', {'estado': 'activa', 'motivo': 'x'}, format='json').status_code, 400)
        self.api.patch(f'{url}/', {'latitud': '-25.3', 'longitud': '-57.6'}, format='json')
        self.api.post(f'{url}/estado/', {'estado': 'activa', 'motivo': 'x'}, format='json')
        r = self.api.patch(f'{url}/', {'latitud': None, 'longitud': None}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.api.patch(f'{url}/', {'metodo_ubicacion': 'sin_ubicacion'}, format='json')
        self.assertEqual(r.data['metodo_ubicacion'], 'manual')  # con coordenadas no puede quedar «sin ubicación»

    def test_titular_futuro_y_lectura_maxima(self):
        _, _, _, conexion, medidor = self.armar_basico(self.api)
        otro = self.crear(self.api, 'clientes/', {'nombre': 'Futuro'})
        r = self.api.post(f'/api/v1/conexiones/{conexion["Code"]}/titular/', {'cliente': otro['Code'], 'desde': '2999-01-01', 'motivo': 'x'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.api.post(f'/api/v1/conexiones/{conexion["Code"]}/instalar-medidor/', {'medidor': medidor['Code'], 'fecha': '2026-01-01', 'lectura_inicial': '500'}, format='json')
        r = self.api.patch(f'/api/v1/medidores/{medidor["Code"]}/', {'lectura_maxima': '100'}, format='json')
        self.assertEqual(r.status_code, 400)
