"""
Pruebas de la Fase 3: recorridos y lecturas.

Casos obligatorios de la sección 21: 2 (el cobrador no accede a conexiones fuera de su asignación), 3 (no hay
lectura sin foto), 4 (duplicadas: procedimiento explícito), 5 (la lectura histórica conserva el medidor tras una
sustitución), 6 (el consumo lo calcula el servidor), 18 (sin borrado físico) y 20 (fotos privadas).
Criterio de aceptación: un cobrador completa un recorrido y sincroniza lecturas sin duplicar registros.
"""
import shutil
import tempfile
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auditoria.models import RegistroAuditoria
from apps.lecturas.models import Lectura
from apps.padron import servicios as padron
from apps.padron.models import Conexion, Medidor
from apps.recorridos import servicios as recorridos
from apps.recorridos.models import Recorrido
from apps.territorio.models import Barrio, Zona
from comun.pruebas.utilidades import LimpiarLimites, admin_de, cliente_de, nueva_institucion, usuario_con_permisos

JPG = b'\xff\xd8\xff\xe0' + b'\x00' * 200
PERIODO = '2026-10'


def foto(nombre='medidor.jpg'):
    return SimpleUploadedFile(nombre, JPG, content_type='image/jpeg')


class BaseLecturas(LimpiarLimites, TestCase):
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
        zona = Zona.objects.create(institucion=self.a, Code='Z1', nombre='Centro')
        self.barrio = Barrio.objects.create(institucion=self.a, zona=zona, Code='B1', nombre='San Roque')
        cliente = padron.crear_cliente(institucion=self.a, datos={'Code': 'C1', 'nombre': 'María Benítez'})
        self.conexiones, self.medidores = [], []
        for n in (1, 2, 3):
            conexion = padron.crear_conexion(institucion=self.a, datos={
                'Code': f'CX{n}', 'cliente': cliente, 'barrio': self.barrio, 'direccion': f'Calle {n}',
                'latitud': Decimal('-25.250000'), 'longitud': Decimal('-57.550000')})
            medidor = padron.crear_medidor(institucion=self.a, datos={'Code': f'M{n}', 'lectura_maxima': Decimal('99999')})
            padron.instalar_medidor(conexion, medidor, fecha=date(2026, 1, 1), lectura_inicial=Decimal('100'))
            self.conexiones.append(conexion)
            self.medidores.append(medidor)
        self.cobrador = usuario_con_permisos(self.a, 'cob1', ['lecturas.registrar'])
        self.otro_cobrador = usuario_con_permisos(self.a, 'cob2', ['lecturas.registrar'])
        self.recorrido = recorridos.crear_recorrido(institucion=self.a, datos={'Code': 'R1', 'nombre': 'Centro', 'periodo': PERIODO})
        recorridos.agregar_conexiones(self.recorrido, conexiones=self.conexiones[:2])
        recorridos.asignar_cobrador(self.recorrido, self.cobrador)
        recorridos.cambiar_estado(self.recorrido, 'abierto')
        self.cob = cliente_de(self.a, 'cob1')

    def tearDown(self):
        self._ajustes.disable()
        shutil.rmtree(self._privado, ignore_errors=True)
        super().tearDown()

    def datos(self, medidor='M1', lectura='112.5', **extra):
        return {'id_operacion': str(uuid.uuid4()), 'recorrido': 'R1', 'medidor': medidor, 'lectura_actual': lectura,
                'capturada_en': timezone.now().isoformat(), 'latitud': '-25.250100', 'longitud': '-57.550100',
                'precision_metros': '8.4', 'foto': foto(), **extra}

    def enviar(self, api=None, codigo=201, **kwargs):
        cuerpo = self.datos(**kwargs)
        cuerpo = {k: v for k, v in cuerpo.items() if v is not None}
        r = (api or self.cob).post('/api/v1/cobrador/lecturas/', cuerpo, format='multipart')
        self.assertEqual(r.status_code, codigo, getattr(r, 'data', r.content))
        return r.data


class RegistroTests(BaseLecturas):
    def test_el_consumo_lo_calcula_el_servidor(self):
        datos = self.enviar(lectura='112.5', consumo='99999')  # un «consumo» del teléfono se ignora
        self.assertEqual((datos['estado'], Decimal(datos['consumo']), Decimal(datos['lectura_anterior'])),
                         ('confirmada', Decimal('12.5'), Decimal('100')))
        self.assertEqual(datos['origen_anterior'], 'instalacion')
        self.assertTrue(datos['comprobante'].startswith('L-'))
        self.assertEqual(datos['deudas']['facturas'], [])
        lectura = Lectura.objects.get()
        self.assertEqual((lectura.precision_metros, lectura.distancia_metros < 50), (8, True))

    def test_se_identifica_el_medidor_por_su_numero(self):
        padron.actualizar_medidor(self.medidores[1], {'numero': 'xz-900'})
        paquete = self.cob.get('/api/v1/cobrador/recorridos/R1/paquete/').data['conexiones']
        self.assertEqual([(c['orden'], c['medidor'], c['medidor_numero']) for c in paquete],
                         [(1, 'M1', ''), (2, 'M2', 'XZ-900')])
        datos = self.enviar(medidor='Xz-900', lectura='105')
        self.assertEqual((datos['medidor'], datos['medidor_numero']), ('M2', 'XZ-900'))
        self.enviar(medidor='NO-EXISTE', codigo=400)

    def test_sin_foto_o_sin_gps_no_hay_lectura(self):
        self.enviar(foto=None, codigo=400)
        self.enviar(latitud=None, longitud=None, codigo=400)
        self.enviar(foto=SimpleUploadedFile('x.jpg', b'no soy una foto'), codigo=400)
        self.assertFalse(Lectura.objects.exists())

    def test_foto_de_galeria_solo_si_la_institucion_la_permite(self):
        # Sin habilitar no se pierde (pudo venir de un paquete viejo): queda en revisión.
        r = self.enviar(foto_origen='galeria')
        self.assertEqual((r['estado'], r['motivo_revision']), ('requiere_revision', 'galeria_no_permitida'))
        self.a.lecturas_permite_galeria = True
        self.a.save()
        r = self.enviar(medidor='M2', foto_origen='galeria')
        self.assertEqual((r['foto_origen'], r['estado']), ('galeria', 'confirmada'))

    def test_reenviar_la_misma_operacion_no_duplica(self):
        cuerpo = self.datos()
        primero = self.cob.post('/api/v1/cobrador/lecturas/', cuerpo, format='multipart')
        cuerpo['foto'] = foto()
        segundo = self.cob.post('/api/v1/cobrador/lecturas/', cuerpo, format='multipart')
        self.assertEqual((primero.status_code, segundo.status_code), (201, 200))
        self.assertTrue(segundo.data['ya_recibida'])
        self.assertEqual(primero.data['comprobante'], segundo.data['comprobante'])
        self.assertEqual(Lectura.objects.count(), 1)

    def test_otra_lectura_del_mismo_periodo_queda_en_revision(self):
        self.enviar(lectura='110')
        segunda = self.enviar(lectura='111')
        self.assertEqual((segunda['estado'], segunda['motivo_revision'], segunda['consumo']),
                         ('requiere_revision', 'duplicada', None))
        # La base impide dos confirmadas aunque alguien se saltee el servicio.
        lectura = Lectura.objects.get(comprobante=segunda['comprobante'])
        lectura.estado, lectura.consumo = 'confirmada', Decimal('11')
        with self.assertRaises(IntegrityError), transaction.atomic():
            lectura.save()

    def test_lectura_menor_que_la_anterior_queda_en_revision_sin_consumo(self):
        datos = self.enviar(lectura='50')
        self.assertEqual((datos['estado'], datos['motivo_revision'], datos['consumo']),
                         ('requiere_revision', 'lectura_menor', None))

    def test_lectura_mayor_que_la_capacidad_se_rechaza(self):
        self.enviar(lectura='100000', codigo=400)

    def test_fecha_futura_queda_en_revision(self):
        r = self.enviar(capturada_en=(timezone.now() + timedelta(days=1)).isoformat())
        self.assertEqual(r['motivo_revision'], 'fecha_dudosa')


class AsignacionTests(BaseLecturas):
    def test_el_cobrador_no_lee_fuera_de_su_asignacion(self):
        # Conexión que no está en el recorrido (o se quitó mientras estaba sin conexión): no se pierde, va a revisión
        # y el cobrador no ve los datos del titular.
        r = self.enviar(medidor='M3')
        self.assertEqual((r['estado'], r['motivo_revision'], r['titular'], r['conexion']),
                         ('requiere_revision', 'fuera_del_recorrido', '', ''))
        # Recorrido al que no está asignado.
        otro = cliente_de(self.a, 'cob2')
        self.assertEqual(self.enviar(api=otro, codigo=400)['codigo'], 'fuera_de_asignacion')
        self.assertEqual(otro.get('/api/v1/cobrador/recorridos/R1/paquete/').status_code, 404)
        self.assertEqual(otro.get('/api/v1/cobrador/recorridos/').data, [])
        # Medidor de otra institución.
        cliente_b = padron.crear_cliente(institucion=self.b, datos={'Code': 'C1', 'nombre': 'B'})
        conexion_b = padron.crear_conexion(institucion=self.b, datos={'Code': 'CXB', 'cliente': cliente_b})
        medidor_b = padron.crear_medidor(institucion=self.b, datos={'Code': 'MB'})
        padron.instalar_medidor(conexion_b, medidor_b, fecha=date(2026, 1, 1), lectura_inicial=Decimal('0'))
        self.assertEqual(self.enviar(medidor='MB', codigo=400)['codigo'], 'medidor_inexistente')
        # Sin el permiso no entra al modo cobrador, aunque sea de la misma institución.
        usuario_con_permisos(self.a, 'oficina', ['padron.consultar'])
        self.assertEqual(cliente_de(self.a, 'oficina').get('/api/v1/cobrador/recorridos/').status_code, 403)
        self.assertEqual(Lectura.objects.count(), 1)  # solo la de M3, en revisión

    def test_las_lecturas_ajenas_no_se_ven(self):
        datos = self.enviar()
        recorridos.asignar_cobrador(self.recorrido, self.otro_cobrador)
        otro = cliente_de(self.a, 'cob2')
        self.assertEqual(otro.get(f'/api/v1/cobrador/lecturas/{datos["comprobante"]}/').status_code, 404)
        self.assertEqual(self.cob.get(f'/api/v1/cobrador/lecturas/{datos["comprobante"]}/').status_code, 200)

    def test_recorrido_cerrado_o_asignacion_retirada_mientras_estaba_sin_conexion(self):
        recorridos.cambiar_estado(self.recorrido, 'cerrado')
        self.assertEqual(self.enviar()['motivo_revision'], 'recorrido_cerrado')
        recorridos.cambiar_estado(self.recorrido, 'abierto', motivo='faltaron lecturas')
        recorridos.retirar_cobrador(self.recorrido, self.cobrador)
        self.assertEqual(self.enviar(medidor='M2')['motivo_revision'], 'asignacion_retirada')

    def test_paquete_para_trabajar_sin_conexion(self):
        self.assertEqual(self.cob.post('/api/v1/cobrador/recorridos/R1/iniciar/').status_code, 200)
        self.enviar()
        paquete = self.cob.get('/api/v1/cobrador/recorridos/R1/paquete/').data
        self.assertEqual([c['conexion'] for c in paquete['conexiones']], ['CX1', 'CX2'])
        primera = paquete['conexiones'][0]
        self.assertEqual((primera['medidor'], Decimal(primera['lectura_anterior']), primera['leida']['estado']),
                         ('M1', Decimal('100'), 'confirmada'))
        self.assertNotIn('id', primera)
        # Foto de la vivienda: solo de conexiones del recorrido.
        padron.guardar_foto_vivienda(self.conexiones[0], SimpleUploadedFile('c.jpg', JPG))
        padron.guardar_foto_vivienda(self.conexiones[2], SimpleUploadedFile('c.jpg', JPG))
        self.assertEqual(self.cob.get('/api/v1/cobrador/recorridos/R1/foto-vivienda/CX1/').status_code, 200)
        self.assertEqual(self.cob.get('/api/v1/cobrador/recorridos/R1/foto-vivienda/CX3/').status_code, 404)
        self.assertEqual(self.cob.get('/api/v1/conexiones/CX1/foto-vivienda/').status_code, 403)
        self.assertEqual(self.cob.post('/api/v1/cobrador/recorridos/R1/finalizar/').status_code, 200)


class HistorialTests(BaseLecturas):
    def test_la_lectura_conserva_el_medidor_tras_la_sustitucion(self):
        datos = self.enviar(lectura='150')
        nuevo = padron.crear_medidor(institucion=self.a, datos={'Code': 'M9'})
        padron.sustituir_medidor(self.conexiones[0], nuevo, fecha=timezone.localdate(), lectura_retiro=Decimal('160'),
                                 lectura_inicial=Decimal('0'), motivo='Trabado')
        lectura = Lectura.objects.get(comprobante=datos['comprobante'])
        self.assertEqual((lectura.medidor.Code, lectura.instalacion.medidor.Code), ('M1', 'M1'))
        r = self.api.get(f'/api/v1/lecturas/{datos["comprobante"]}/')
        self.assertEqual(r.data['medidor'], 'M1')

    def test_lectura_tomada_antes_de_una_sustitucion_queda_en_revision(self):
        cuerpo = self.datos(capturada_en=(timezone.now() - timedelta(days=2)).isoformat())
        nuevo = padron.crear_medidor(institucion=self.a, datos={'Code': 'M9'})
        padron.sustituir_medidor(self.conexiones[0], nuevo, fecha=timezone.localdate(), lectura_retiro=Decimal('160'),
                                 lectura_inicial=Decimal('0'), motivo='Trabado')
        r = self.cob.post('/api/v1/cobrador/lecturas/', cuerpo, format='multipart')
        self.assertEqual((r.status_code, r.data['motivo_revision'], r.data['medidor']), (201, 'medidor_cambiado', 'M1'))

    def test_la_lectura_anterior_es_la_ultima_confirmada(self):
        self.enviar(lectura='130')
        siguiente = recorridos.crear_recorrido(institucion=self.a, datos={'Code': 'R2', 'nombre': 'Nov', 'periodo': '2026-11'})
        recorridos.agregar_conexiones(siguiente, conexiones=[self.conexiones[0]])
        recorridos.asignar_cobrador(siguiente, self.cobrador)
        recorridos.cambiar_estado(siguiente, 'abierto')
        datos = self.enviar(recorrido='R2', lectura='145')
        self.assertEqual((Decimal(datos['lectura_anterior']), Decimal(datos['consumo']), datos['origen_anterior']),
                         (Decimal('130'), Decimal('15'), 'lectura'))


class RevisionTests(BaseLecturas):
    def setUp(self):
        super().setUp()
        self.revisor = cliente_de(self.a)  # admin

    def test_autorizar_lectura_menor_exige_consumo(self):
        datos = self.enviar(lectura='5')
        url = f'/api/v1/lecturas/{datos["comprobante"]}'
        r = self.revisor.post(f'{url}/autorizar/', {'motivo': 'El contador volvió a cero'}, format='json')
        self.assertEqual(r.data['codigo'], 'consumo_requerido')
        r = self.revisor.post(f'{url}/autorizar/', {'motivo': 'Volvió a cero', 'consumo': '-1'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.revisor.post(f'{url}/autorizar/', {'motivo': 'Volvió a cero', 'consumo': '9904'}, format='json')
        self.assertEqual((r.status_code, r.data['estado'], Decimal(r.data['consumo'])), (200, 'confirmada', Decimal('9904')))
        self.assertTrue(RegistroAuditoria.objects.filter(accion='lectura_autorizada', motivo='Volvió a cero').exists())

    def test_duplicada_se_resuelve_anulando_una(self):
        primera = self.enviar(lectura='110')
        segunda = self.enviar(lectura='111')
        url = f'/api/v1/lecturas/{segunda["comprobante"]}'
        self.assertEqual(self.revisor.post(f'{url}/autorizar/', {'motivo': 'x'}, format='json').status_code, 400)
        self.revisor.post(f'/api/v1/lecturas/{primera["comprobante"]}/anular/', {'motivo': 'Error de tipeo'}, format='json')
        r = self.revisor.post(f'{url}/autorizar/', {'motivo': 'La buena es esta'}, format='json')
        self.assertEqual((r.data['estado'], Decimal(r.data['consumo'])), ('confirmada', Decimal('11')))

    def test_corregir_recalcula_y_no_toca_si_hay_posteriores(self):
        datos = self.enviar(lectura='120')
        url = f'/api/v1/lecturas/{datos["comprobante"]}'
        r = self.revisor.post(f'{url}/corregir/', {'lectura_actual': '121', 'motivo': 'Se ve 121 en la foto'}, format='json')
        self.assertEqual(Decimal(r.data['consumo']), Decimal('21'))
        r = self.revisor.post(f'{url}/corregir/', {'lectura_actual': '90', 'motivo': 'x'}, format='json')
        self.assertEqual((r.data['estado'], r.data['consumo']), ('requiere_revision', None))
        self.revisor.post(f'{url}/autorizar/', {'motivo': 'ok', 'consumo': '0'}, format='json')
        siguiente = recorridos.crear_recorrido(institucion=self.a, datos={'Code': 'R2', 'nombre': 'Nov', 'periodo': '2026-11'})
        recorridos.agregar_conexiones(siguiente, conexiones=[self.conexiones[0]])
        recorridos.asignar_cobrador(siguiente, self.cobrador)
        recorridos.cambiar_estado(siguiente, 'abierto')
        self.enviar(recorrido='R2', lectura='95')
        r = self.revisor.post(f'{url}/corregir/', {'lectura_actual': '91', 'motivo': 'x'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.revisor.post(f'{url}/anular/', {'motivo': 'x'}, format='json').status_code, 400)

    def test_permisos_de_revision_y_sin_borrado(self):
        datos = self.enviar()
        usuario_con_permisos(self.a, 'consulta', ['lecturas.consultar'])
        consulta = cliente_de(self.a, 'consulta')
        url = f'/api/v1/lecturas/{datos["comprobante"]}'
        self.assertEqual(consulta.get(f'{url}/').status_code, 200)
        self.assertEqual(consulta.post(f'{url}/anular/', {'motivo': 'x'}, format='json').status_code, 403)
        self.assertEqual(self.cob.get('/api/v1/lecturas/').status_code, 403)  # el cobrador no ve todas
        self.assertEqual(self.revisor.delete(f'{url}/').status_code, 405)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Medidor.objects.get(institucion=self.a, Code='M1').delete()  # PROTECT: tiene lecturas

    def test_fotos_privadas_y_comprobante(self):
        datos = self.enviar(adicionales=[foto('a.jpg'), foto('b.jpg')])
        url = f'/api/v1/lecturas/{datos["comprobante"]}'
        detalle = self.revisor.get(f'{url}/').data
        self.assertEqual([f['principal'] for f in detalle['fotos']], [True, False, False])
        r = self.revisor.get(f'{url}/fotos/0/')
        self.assertEqual((r.status_code, r['Content-Type']), (200, 'image/jpeg'))
        self.assertEqual(self.revisor.get(f'{url}/fotos/9/').status_code, 404)
        self.assertEqual(APIClient().get(f'{url}/fotos/0/').status_code, 401)
        self.assertEqual(cliente_de(self.b).get(f'{url}/fotos/0/').status_code, 404)
        pdf = self.revisor.get(f'{url}/comprobante/')
        self.assertEqual((pdf.status_code, pdf['Content-Type'], pdf.content[:5]), (200, 'application/pdf', b'%PDF-'))
        self.assertEqual(self.cob.get(f'/api/v1/cobrador/lecturas/{datos["comprobante"]}/comprobante/').status_code, 200)

    def test_lista_con_filtros(self):
        self.enviar()
        self.enviar(medidor='M2', lectura='50')
        lista = self.revisor.get('/api/v1/lecturas/?estado=requiere_revision').data
        self.assertEqual([l['conexion'] for l in lista['results']], ['CX2'])
        self.assertEqual(self.revisor.get('/api/v1/lecturas/?conexion=cx1').data['count'], 1)
        self.assertEqual(self.revisor.get(f'/api/v1/lecturas/?periodo={PERIODO}&recorrido=R1').data['count'], 2)


class RecorridosTests(BaseLecturas):
    def test_armado_por_barrio_orden_y_progreso(self):
        r = self.api.post('/api/v1/recorridos/', {'Code': 'r3', 'nombre': 'Todo', 'periodo': '2026-12'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        r = self.api.post('/api/v1/recorridos/R3/agregar-conexiones/', {'barrio': 'B1'}, format='json')
        self.assertEqual(sorted(r.data['agregadas']), ['CX1', 'CX2', 'CX3'])
        # La misma conexión no entra en dos recorridos del mismo período.
        r = self.api.post('/api/v1/recorridos/R1/agregar-conexiones/', {'conexiones': ['CX3']}, format='json')
        self.assertEqual(r.data['en_otro_recorrido'], [])  # R1 es de otro período: entra
        otro = self.api.post('/api/v1/recorridos/', {'Code': 'R4', 'nombre': 'x', 'periodo': '2026-12'}, format='json')
        self.assertEqual(otro.status_code, 201)
        r = self.api.post('/api/v1/recorridos/R4/agregar-conexiones/', {'conexiones': ['CX1']}, format='json')
        self.assertEqual(r.data['en_otro_recorrido'], [{'conexion': 'CX1', 'recorrido': 'R3'}])
        r = self.api.post('/api/v1/recorridos/R3/ordenar/', {'conexiones': ['CX3', 'CX1', 'CX2']}, format='json')
        self.assertEqual(r.status_code, 200)
        filas = self.api.get('/api/v1/recorridos/R3/conexiones/').data
        self.assertEqual([f['conexion'] for f in filas], ['CX3', 'CX1', 'CX2'])
        self.assertEqual(self.api.post('/api/v1/recorridos/R3/ordenar/', {'conexiones': ['CX3']}, format='json').status_code, 400)

    def test_abrir_exige_conexiones_y_cobrador_y_el_periodo_no_cambia(self):
        self.api.post('/api/v1/recorridos/', {'Code': 'R5', 'nombre': 'x', 'periodo': '2026-12'}, format='json')
        self.assertEqual(self.api.post('/api/v1/recorridos/R5/estado/', {'estado': 'abierto'}, format='json').status_code, 400)
        self.assertEqual(self.api.patch('/api/v1/recorridos/R5/', {'periodo': '2027-01'}, format='json').status_code, 400)
        self.assertEqual(self.api.post('/api/v1/recorridos/', {'Code': 'R6', 'nombre': 'x', 'periodo': '2026-13'},
                                       format='json').status_code, 400)
        self.api.post('/api/v1/recorridos/R5/agregar-conexiones/', {'conexiones': ['CX3']}, format='json')
        self.assertEqual(self.api.post('/api/v1/recorridos/R5/asignar-cobrador/', {'usuario': 'admin'},
                                       format='json').status_code, 200)  # el admin tiene todos los permisos
        usuario_con_permisos(self.a, 'sinpermiso', ['padron.consultar'])
        self.assertEqual(self.api.post('/api/v1/recorridos/R5/asignar-cobrador/', {'usuario': 'sinpermiso'},
                                       format='json').status_code, 400)
        self.assertEqual(self.api.post('/api/v1/recorridos/R5/estado/', {'estado': 'abierto'}, format='json').status_code, 200)

    def test_no_se_quita_una_conexion_con_lectura_y_avance(self):
        self.enviar()
        r = self.api.post('/api/v1/recorridos/R1/quitar-conexion/', {'conexion': 'CX1'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.api.post('/api/v1/recorridos/R1/quitar-conexion/', {'conexion': 'CX2'}, format='json')
        self.assertEqual(r.data['avance'], {'total': 1, 'leidas': 1, 'confirmadas': 1, 'en_revision': 0, 'pendientes': 0})
        self.assertEqual(self.api.delete('/api/v1/recorridos/R1/').status_code, 405)

    def test_filtros_del_mapa(self):
        self.enviar()
        r = self.api.get(f'/api/v1/mapa/?lectura=sin&periodo={PERIODO}').data
        self.assertEqual(sorted(c['Code'] for c in r['conexiones']), ['CX2', 'CX3'])
        self.assertEqual(self.api.get(f'/api/v1/conexiones/?lectura=con&periodo={PERIODO}').data['count'], 1)
        self.assertEqual(self.api.get('/api/v1/conexiones/?recorrido=r1').data['count'], 2)
        self.assertEqual(self.api.get('/api/v1/conexiones/?cobrador=cob1').data['count'], 2)

    def test_aceptacion_un_cobrador_completa_su_recorrido_sin_duplicar(self):
        """Criterio de aceptación de la Fase 3, con reintentos de sincronización."""
        self.cob.post('/api/v1/cobrador/recorridos/R1/iniciar/')
        paquete = self.cob.get('/api/v1/cobrador/recorridos/R1/paquete/').data
        operaciones = []
        for n, conexion in enumerate(paquete['conexiones']):
            cuerpo = self.datos(medidor=conexion['medidor'], lectura=str(Decimal(conexion['lectura_anterior']) + 10 + n))
            operaciones.append(cuerpo)
            self.assertEqual(self.cob.post('/api/v1/cobrador/lecturas/', cuerpo, format='multipart').status_code, 201)
        for cuerpo in operaciones:  # el teléfono no recibió las respuestas y reintenta todo
            cuerpo['foto'] = foto()
            self.assertEqual(self.cob.post('/api/v1/cobrador/lecturas/', cuerpo, format='multipart').status_code, 200)
        self.cob.post('/api/v1/cobrador/recorridos/R1/finalizar/')
        self.assertEqual(Lectura.objects.count(), 2)
        detalle = self.api.get('/api/v1/recorridos/R1/').data
        self.assertEqual(detalle['avance']['pendientes'], 0)
        self.assertIsNotNone(detalle['cobradores'][0]['finalizado_en'])
        self.assertEqual(Conexion.objects.count(), 3)
        self.assertEqual(Recorrido.objects.get(Code='R1').estado, 'abierto')


class CasosDeLaRevisionTests(BaseLecturas):
    """Casos que encontró la revisión independiente de la Fase 3."""

    def abrir(self, code, periodo, conexiones):
        r = recorridos.crear_recorrido(institucion=self.a, datos={'Code': code, 'nombre': code, 'periodo': periodo})
        recorridos.agregar_conexiones(r, conexiones=conexiones)
        recorridos.asignar_cobrador(r, self.cobrador)
        recorridos.cambiar_estado(r, 'abierto')
        return r

    def test_lectura_de_un_periodo_anterior_que_llega_despues_no_duplica_consumo(self):
        self.enviar(lectura='112.5')  # octubre confirmada
        self.abrir('R-SEP', '2026-09', [self.conexiones[0]])
        sep = self.enviar(recorrido='R-SEP', lectura='105')
        self.assertEqual((sep['estado'], sep['motivo_revision']), ('requiere_revision', 'posterior_existente'))
        r = self.api.post(f'/api/v1/lecturas/{sep["comprobante"]}/autorizar/', {'motivo': 'x'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_autorizar_recalcula_la_lectura_anterior(self):
        recorridos.cambiar_estado(self.recorrido, 'cerrado')
        octubre = self.enviar(lectura='120')  # llega con el recorrido cerrado: a revisión, anterior = 100
        self.assertEqual((octubre['motivo_revision'], Decimal(octubre['lectura_anterior'])), ('recorrido_cerrado', Decimal('100')))
        self.abrir('R-SEP', '2026-09', [self.conexiones[0]])
        septiembre = self.enviar(recorrido='R-SEP', lectura='110')
        self.assertEqual(septiembre['motivo_revision'], 'posterior_existente')
        r = self.api.post(f'/api/v1/lecturas/{septiembre["comprobante"]}/autorizar/', {'motivo': 'ok'}, format='json')
        self.assertEqual(Decimal(r.data['consumo']), Decimal('10'))
        r = self.api.post(f'/api/v1/lecturas/{octubre["comprobante"]}/autorizar/', {'motivo': 'ok'}, format='json')
        self.assertEqual((Decimal(r.data['lectura_anterior']), Decimal(r.data['consumo'])), (Decimal('110'), Decimal('10')))
        # Con octubre confirmado, septiembre ya no se anula ni corrige.
        url = f'/api/v1/lecturas/{septiembre["comprobante"]}'
        self.assertEqual(self.api.post(f'{url}/anular/', {'motivo': 'x'}, format='json').status_code, 400)

    def test_medidor_movido_a_otra_conexion_despues_de_leer_sin_conexion(self):
        cuerpo = self.datos(capturada_en=(timezone.now() - timedelta(days=1)).isoformat())
        recorridos.agregar_conexiones(self.recorrido, conexiones=[self.conexiones[2]])
        padron.retirar_medidor(self.conexiones[0], fecha=timezone.localdate(), lectura_retiro=Decimal('113'),
                               motivo='Se mueve', estado_medidor='disponible')
        padron.retirar_medidor(self.conexiones[2], fecha=timezone.localdate(), lectura_retiro=Decimal('100'),
                               motivo='x', estado_medidor='disponible')
        padron.instalar_medidor(self.conexiones[2], self.medidores[0], fecha=timezone.localdate(), lectura_inicial=Decimal('113'))
        r = self.cob.post('/api/v1/cobrador/lecturas/', cuerpo, format='multipart')
        lectura = Lectura.objects.get(comprobante=r.data['comprobante'])
        self.assertEqual((lectura.conexion.Code, lectura.motivo_revision), ('CX1', 'medidor_cambiado'))

    def test_corregir_conserva_el_motivo_original(self):
        self.enviar(lectura='110')
        dup = self.enviar(lectura='111')
        r = self.api.post(f'/api/v1/lecturas/{dup["comprobante"]}/corregir/', {'lectura_actual': '90', 'motivo': 'x'}, format='json')
        self.assertEqual(r.data['motivo_revision'], 'duplicada')

    def test_foto_adicional_invalida_no_deja_archivos_sueltos(self):
        antes = sum(1 for _ in Path(self._privado).rglob('*') if _.is_file())
        self.enviar(adicionales=[SimpleUploadedFile('x.jpg', b'no es foto')], codigo=400)
        despues = sum(1 for _ in Path(self._privado).rglob('*') if _.is_file())
        self.assertEqual((antes, Lectura.objects.count()), (despues, 0))

    def test_no_se_reordena_un_recorrido_cerrado(self):
        recorridos.cambiar_estado(self.recorrido, 'cerrado')
        r = self.api.post('/api/v1/recorridos/R1/ordenar/', {'conexiones': ['CX2', 'CX1']}, format='json')
        self.assertEqual(r.status_code, 400)
