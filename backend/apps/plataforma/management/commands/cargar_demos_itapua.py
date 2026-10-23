"""
Crea dos aguateras de DEMOSTRACIÓN en Itapúa, cada una con 20 abonados, sus medidores y tres meses de historial:

  DEMO-ENC  Aguatera Demo Encarnación  (zona de Encarnación)
  DEMO-CAM  Junta de Saneamiento Demo Cambyretá  (zona de Cambyretá)

Cada una queda con facturación autoimpresa, tarifa residencial, zonas y barrios con sus conexiones ubicadas en el
mapa, tres recorridos ya leídos (liquidaciones), facturas contado y a crédito con pagos y recibos del mes más
antiguo, deuda pendiente en los meses siguientes y el recorrido del mes abierto para el cobrador.

Uso: python manage.py cargar_demos_itapua [--solo DEMO-ENC|DEMO-CAM]
Idempotente: una aguatera que ya tiene conexiones no se toca. Solo para demostración.
Usuarios: admin, cobrador1 y cajero1, los tres con la contraseña Acceso*2026 (no se pide cambiarla).
Al repetir el comando también se restablece esa contraseña en los tres.
"""
import random
import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.caja import servicios as caja
from apps.caja.models import Caja
from apps.cobranzas import servicios as cobranzas
from apps.cobranzas.models import FormaPago
from apps.facturacion import facturas
from apps.facturacion import servicios as numeracion
from apps.identidad.models import Permiso, Rol, Usuario
from apps.lecturas import servicios as lecturas
from apps.padron import servicios as padron
from apps.padron.models import Conexion
from apps.plataforma.management.commands.cargar_datos_prueba import FOTO, TARIFA, _mes
from apps.plataforma.models import Institucion
from apps.plataforma.servicios import crear_institucion
from apps.recorridos import servicios as recorridos
from apps.tarifas import servicios as tarifas
from apps.territorio.models import Barrio, Zona

CONTRASENA = 'Acceso*2026'      # la misma para admin, cobrador1 y cajero1 (botones «Acceso como demo» del ingreso)


def _usuario(institucion, nombre_usuario, nombre, roles):
    usuario = Usuario(institucion=institucion, nombre_usuario=nombre_usuario, nombre=nombre)
    usuario.set_password(CONTRASENA)
    usuario.save()
    usuario.roles.set(roles)
    return usuario

NOMBRES = [
    'María Benítez', 'Juan Ortiz', 'Rosa Giménez', 'Carlos Duarte', 'Ana Villalba', 'Pedro Cáceres', 'Lucía Ramírez',
    'Miguel Ayala', 'Sofía Martínez', 'Ramón Acosta', 'Teresa Fernández', 'Luis Báez', 'Graciela Romero',
    'Héctor Núñez', 'Norma Aquino', 'Óscar Insfrán', 'Elena Vera', 'Fabián Rolón', 'Silvia Palacios', 'Gustavo Peralta',
]
APELLIDOS_ALTERNOS = ['Franco', 'Barrios', 'Mendoza', 'Portillo', 'Cabrera', 'Samudio', 'Domínguez', 'Colmán',
                      'Riveros', 'Ferreira', 'Bogado', 'Escobar', 'Galeano', 'Lezcano', 'Servín', 'Torales', 'Arce',
                      'Centurión', 'Maidana', 'Zárate']

USUARIOS_DEMO = ('admin', 'cobrador1', 'cajero1')

AGUATERAS = [
    {
        'codigo': 'DEMO-ENC', 'nombre': 'Aguatera Demo Encarnación', 'ruc': '80123456-7',
        'direccion': 'Av. Irrazábal 1250, Encarnación, Itapúa', 'telefono': '(071) 200 100',
        'centro': (Decimal('-27.330600'), Decimal('-55.866700')), 'timbrado': '15234567', 'semilla': 71,
        'zonas': [('CENTRO', 'Centro de Encarnación', '#EA284E', [('CENTRO', 'Centro'), ('SAN-PEDRO', 'San Pedro')]),
                  ('COSTANERA', 'Costanera y Pacú Cuá', '#2B7FFF', [('PACU-CUA', 'Pacú Cuá'),
                                                                     ('VILLA-QUITERIA', 'Villa Quiteria')])],
        'calles': ['Av. Irrazábal', 'Calle Cabañas', 'Calle Mariscal Estigarribia', 'Calle Carlos Antonio López',
                   'Calle Villarrica', 'Av. Japón', 'Calle General Artigas', 'Calle Memmel', 'Calle Tomás Romero Pereira'],
    },
    {
        'codigo': 'DEMO-CAM', 'nombre': 'Junta de Saneamiento Demo Cambyretá', 'ruc': '80765432-1',
        'direccion': 'Ruta 6, Cambyretá, Itapúa', 'telefono': '(071) 240 200',
        'centro': (Decimal('-27.350000'), Decimal('-55.780000')), 'timbrado': '15876543', 'semilla': 83,
        'zonas': [('URBANA', 'Zona urbana', '#EA284E', [('CENTRO', 'Centro'), ('SAN-ISIDRO', 'San Isidro')]),
                  ('RUTA-6', 'Sobre la Ruta 6', '#2B7FFF', [('KM-12', 'Km 12'), ('VIRGEN-FATIMA', 'Virgen de Fátima')])],
        'calles': ['Calle Principal', 'Calle San Isidro', 'Ruta 6 km 12', 'Calle Itapúa', 'Calle Virgen de Fátima',
                   'Calle 14 de Mayo', 'Calle Cerro Corá', 'Calle Defensores del Chaco', 'Calle Independencia'],
    },
]


def _correo(nombre, n):
    base = nombre.split()[0].lower()
    for a, b in (('í', 'i'), ('ú', 'u'), ('á', 'a'), ('é', 'e'), ('ó', 'o'), ('ñ', 'n')):
        base = base.replace(a, b)
    return f'{base}{n}@ejemplo.com'


class Command(BaseCommand):
    help = 'Crea dos aguateras de demostración (Encarnación y Cambyretá) con 20 abonados e historial.'

    def add_arguments(self, parser):
        parser.add_argument('--solo', choices=[a['codigo'] for a in AGUATERAS], help='Crear solo esa aguatera.')

    def handle(self, *args, solo=None, **opciones):
        for datos in AGUATERAS:
            if solo and datos['codigo'] != solo:
                continue
            existente = Institucion.objects.filter(codigo=datos['codigo']).first()
            if existente is not None and Conexion.objects.de(existente).exists():
                for usuario in Usuario.objects.filter(institucion=existente, nombre_usuario__in=USUARIOS_DEMO):
                    usuario.set_password(CONTRASENA)
                    usuario.debe_cambiar_contrasena = False
                    usuario.intentos_fallidos = 0
                    usuario.bloqueado_hasta = None
                    usuario.save()
                self.stdout.write(f'  {datos["codigo"]}: ya tiene datos, no se toca (contraseña de los 3 usuarios '
                                  f'restablecida).')
                continue
            with transaction.atomic():
                self._crear(datos, existente)

    def _crear(self, d, existente):
        rng = random.Random(d['semilla'])
        hoy = timezone.localdate()
        meses = [_mes(hoy, 3), _mes(hoy, 2), _mes(hoy, 1)]       # tres meses ya leídos
        actual = hoy.strftime('%Y-%m')
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n{d["codigo"]} · {d["nombre"]}'))

        institucion = existente or crear_institucion(
            datos={'codigo': d['codigo'], 'nombre': d['nombre'], 'contacto': 'Institución de demostración'},
            admin_usuario='admin', admin_contrasena=CONTRASENA, admin_nombre='Administrador demo',
            admin_correo=f'admin.{d["codigo"].lower()}@ejemplo.com')
        admin = Usuario.objects.get(institucion=institucion, nombre_usuario='admin')
        admin.debe_cambiar_contrasena = False
        admin.save(update_fields=['debe_cambiar_contrasena'])
        institucion.ruc, institucion.direccion, institucion.telefono = d['ruc'], d['direccion'], d['telefono']
        institucion.correo = f'info.{d["codigo"].lower()}@ejemplo.com'
        institucion.modalidad_facturacion = 'autoimpresa'
        institucion.portal_abonados = True
        institucion.save()

        punto = numeracion.crear_punto(institucion=institucion, datos={
            'Code': 'CENTRAL', 'establecimiento': '001', 'punto': '001', 'nombre': 'Oficina central'})
        numeracion.crear_rango(institucion=institucion, datos={
            'Code': 'FAC-DEMO', 'punto': punto, 'tipo_documento': 'factura', 'timbrado': d['timbrado'], 'desde': 1,
            'hasta': 9999, 'vigencia_desde': hoy.replace(month=1, day=1),
            'vigencia_hasta': hoy.replace(year=hoy.year + 1, month=12, day=31)})
        tarifa = tarifas.crear_tarifa(institucion=institucion, datos={'Code': 'RES', 'nombre': 'Residencial'})
        tarifas.crear_version(tarifa, vigente_desde=meses[0].strftime('%Y-%m'), conceptos=TARIFA,
                              observaciones='Tarifa de demostración')

        barrios = []
        for code_zona, nombre_zona, color, lista in d['zonas']:
            zona = Zona.objects.create(institucion=institucion, Code=code_zona, nombre=nombre_zona, color=color)
            barrios += [Barrio.objects.create(institucion=institucion, zona=zona, Code=c, nombre=n) for c, n in lista]

        rol_cobrador = Rol.objects.get(institucion=institucion, Code='COBRADOR')
        rol_cajero, _ = Rol.objects.get_or_create(institucion=institucion, Code='CAJERO', defaults={
            'nombre': 'Cajero', 'descripcion': 'Factura, cobra, maneja su caja y registra gastos (demostración).'})
        rol_cajero.permisos.set(Permiso.objects.filter(codigo__in=[
            'padron.consultar', 'facturacion.emitir', 'facturacion.consultar', 'cobranzas.registrar',
            'cobranzas.consultar', 'caja.operar', 'gastos.registrar', 'gastos.consultar', 'liquidaciones.consultar']))
        cobrador = _usuario(institucion, 'cobrador1', 'Cobrador de demostración', [rol_cobrador])
        cajero = _usuario(institucion, 'cajero1', 'Cajero de demostración', [rol_cajero])

        # --- Padrón: 20 abonados con su conexión ubicada y su medidor -------------------------------------
        centro_lat, centro_lng = d['centro']
        conexiones, instalacion = [], _mes(hoy, 4)
        for n, nombre in enumerate(NOMBRES, start=1):
            if d['codigo'] == 'DEMO-CAM':               # otros apellidos: no se repiten las personas entre aguateras
                nombre = f'{nombre.split()[0]} {APELLIDOS_ALTERNOS[n - 1]}'
            calle = d['calles'][(n * 7) % len(d['calles'])]
            direccion = f'{calle} {rng.randrange(20, 980)}'
            documento = str(rng.randrange(1_200_000, 5_900_000))
            cliente = padron.crear_cliente(institucion=institucion, datos={
                'Code': f'C-{n:04d}', 'nombre': nombre, 'documento': documento, 'direccion_referencia': direccion,
                'correo': _correo(nombre, n), 'telefono': f'098{rng.randrange(1_000_000, 9_999_999)}'})
            lat = centro_lat + Decimal(rng.randrange(-900, 900)) / Decimal(100000)
            lng = centro_lng + Decimal(rng.randrange(-900, 900)) / Decimal(100000)
            conexion = padron.crear_conexion(institucion=institucion, datos={
                'Code': f'CX-{n:04d}', 'cliente': cliente, 'direccion': direccion, 'barrio': barrios[n % len(barrios)],
                'latitud': lat, 'longitud': lng, 'metodo_ubicacion': 'mapa', 'estado': 'activa',
                'fecha_instalacion': instalacion})
            medidor = padron.crear_medidor(institucion=institucion, datos={
                'Code': f'M-{n:04d}', 'numero': f'H{rng.randrange(10000, 99999)}{n:02d}', 'marca': 'Itron', 'modelo': 'Aquadis'})
            inicial = Decimal(rng.randrange(50, 600))
            padron.instalar_medidor(conexion, medidor, fecha=instalacion, lectura_inicial=inicial)
            conexiones.append((conexion, medidor, lat, lng, inicial))
        self.stdout.write(f'  {len(conexiones)} abonados con conexión ubicada y medidor ({len(barrios)} barrios)')

        # --- Historial de lecturas: tres meses leídos y cerrados ---------------------------------------
        base = [rng.choice([6, 8, 10, 12, 14, 18, 22, 27, 35]) for _ in conexiones]
        acumulado = [c[4] for c in conexiones]
        for indice, mes in enumerate(meses):
            periodo = mes.strftime('%Y-%m')
            recorrido = recorridos.crear_recorrido(institucion=institucion, datos={
                'Code': f'R-{periodo}', 'nombre': f'Recorrido {periodo}', 'periodo': periodo})
            recorridos.agregar_conexiones(recorrido, conexiones=[c[0] for c in conexiones])
            recorridos.asignar_cobrador(recorrido, cobrador)
            recorridos.cambiar_estado(recorrido, 'abierto')
            momento = timezone.make_aware(datetime.combine(mes + timedelta(days=14), time(8, 40)))
            for n, (conexion, medidor, lat, lng, _) in enumerate(conexiones):
                consumo = max(1, base[n] + rng.randrange(-3, 4))
                acumulado[n] += consumo
                lecturas.registrar_lectura(institucion=institucion, usuario=cobrador, datos={
                    'id_operacion': uuid.uuid4(), 'recorrido': recorrido.Code, 'medidor': medidor.Code,
                    'lectura_actual': acumulado[n], 'capturada_en': momento + timedelta(minutes=9 * n),
                    'latitud': lat, 'longitud': lng, 'comentario': ''},
                    foto=SimpleUploadedFile('medidor.png', FOTO, content_type='image/png'))
            recorridos.cambiar_estado(recorrido, 'cerrado')
        self.stdout.write(f'  Lecturas de {meses[0]:%Y-%m}, {meses[1]:%Y-%m} y {meses[2]:%Y-%m} (liquidadas)')

        self._cobranzas(institucion, cajero, punto, conexiones, meses, rng)

        recorrido = recorridos.crear_recorrido(institucion=institucion, datos={
            'Code': f'R-{actual}', 'nombre': f'Recorrido {actual}', 'periodo': actual})
        recorridos.agregar_conexiones(recorrido, conexiones=[c[0] for c in conexiones])
        recorridos.asignar_cobrador(recorrido, cobrador)
        recorridos.cambiar_estado(recorrido, 'abierto')
        self.stdout.write(f'  Recorrido {recorrido.Code} abierto para cobrador1 (medidores M-0001 … M-0020)')

    def _cobranzas(self, institucion, cajero, punto, conexiones, meses, rng):
        """Historial de cobros: el mes más antiguo se factura (contado y crédito) y en parte se cobra; el resto queda
        como deuda sin facturar."""
        efectivo = FormaPago.objects.get(institucion=institucion, Code='EFECTIVO')
        transferencia = FormaPago.objects.get(institucion=institucion, Code='TRANSFERENCIA')
        sesion = caja.abrir_sesion(institucion=institucion, caja=Caja.objects.get(institucion=institucion, Code='CAJA1'),
                                   usuario=cajero, saldo_inicial=100000)
        periodo = meses[0].strftime('%Y-%m')
        pendientes = {q.conexion_id: q for q in facturas.pendientes_de_facturar(institucion).filter(periodo=periodo)}
        n_contado = n_credito = n_recibos = 0
        for n, (conexion, *_) in enumerate(conexiones, start=1):
            liquidacion = pendientes.get(conexion.pk)
            if liquidacion is None or n > 16:             # los 4 últimos abonados quedan sin facturar (deuda)
                continue
            cliente = conexion.cliente
            if n <= 11:                                   # paga al contado, en efectivo o por transferencia
                forma = efectivo if n % 3 else transferencia
                facturas.emitir(institucion=institucion, cliente=cliente, liquidaciones=[liquidacion],
                                condicion='contado', punto=punto, usuario=cajero, forma_pago=forma,
                                referencia_externa=f'TRF-{rng.randrange(100000, 999999)}' if forma is transferencia else '')
                n_contado += 1
                continue
            factura = facturas.emitir(institucion=institucion, cliente=cliente, liquidaciones=[liquidacion],
                                      condicion='credito', punto=punto, usuario=cajero)
            n_credito += 1
            if n <= 14:                                   # crédito pagado total (13, 14) o parcialmente (12)
                importe = factura.total if n != 12 else (factura.total / 2).quantize(Decimal('1'))
                cobranzas.emitir_recibo(institucion=institucion, cliente=cliente, importe=importe,
                                        forma_pago=efectivo, clave=f'demo-{institucion.codigo}-{n}',
                                        aplicaciones=[(factura, importe)], usuario=cajero)
                n_recibos += 1
        filas = caja.resumen(sesion)
        caja.cerrar_sesion(sesion, declarados={f['forma_pago']: f['esperado'] for f in filas},
                           observaciones='Cierre de demostración', usuario=cajero)
        self.stdout.write(f'  Cobranzas de {periodo}: {n_contado} facturas contado, {n_credito} a crédito '
                          f'({n_recibos} con recibo), caja cerrada; el resto de los meses queda como deuda')
