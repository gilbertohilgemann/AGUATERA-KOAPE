"""
Carga un escenario de PRUEBA completo en una institución de demostración (por defecto DEMO), para probar el sistema
de punta a punta: padrón con ubicación, tarifa, numeración de facturas, cobrador con recorrido abierto del mes y dos
meses anteriores ya leídos (con sus liquidaciones listas para facturar y cobrar).

Uso: start.bat datos-prueba   (o: python manage.py cargar_datos_prueba [CODIGO])
Solo para instituciones de demostración. Si ya se cargó antes (con una versión anterior), no agrega nada encima:
solo COMPLETA lo que las versiones nuevas necesitan para probar (correos de los clientes y del admin, número de los
medidores, portal de abonados, la clienta de DEMO2).
"""
import base64
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.facturacion import servicios as numeracion
from apps.identidad.models import Permiso, Rol, Usuario
from apps.lecturas import servicios as lecturas
from apps.padron import servicios as padron
from apps.padron.models import Conexion
from apps.plataforma.models import Institucion
from apps.recorridos import servicios as recorridos
from apps.tarifas import servicios as tarifas
from apps.territorio.models import Barrio, Zona

# Foto mínima válida (PNG 1×1) para las lecturas de los meses anteriores.
FOTO = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
CONTRASENA = 'Prueba.Koape.2026'
CLIENTES = [
    ('María Benítez', 'Calle Palma 120', '1234567'), ('Juan Ortiz', 'Calle Palma 245', '2345678'),
    ('Rosa Giménez', 'Avda. Mcal. López 310', '3456789'), ('Carlos Duarte', 'Avda. Mcal. López 455', ''),
    ('Ana Villalba', 'Calle 14 de Mayo 80', '4567890'), ('Pedro Cáceres', 'Calle 14 de Mayo 155', '5678901'),
    ('Lucía Ramírez', 'Calle Cerro Corá 22', ''), ('Escuela Básica N° 512', 'Calle Cerro Corá 90', '80099999-1'),
]
CONSUMOS = [(8, 11), (15, 13), (22, 25), (10, 9), (12, 18), (30, 27), (5, 7), (40, 38)]  # m³ de cada mes anterior
TARIFA = [
    {'orden': 1, 'nombre': 'Consumo mínimo (10 m³)', 'tipo': 'minimo', 'cantidad': '10', 'precio': '2500', 'iva': '10'},
    {'orden': 2, 'nombre': 'Excedente', 'tipo': 'excedente', 'precio': '3000', 'iva': '10'},
    {'orden': 3, 'nombre': 'Tasa ERSSAN', 'tipo': 'porcentaje', 'porcentaje': '2', 'iva': 'exento'},
]


def _mes(fecha: date, atras: int) -> date:
    anio, mes = fecha.year, fecha.month - atras
    while mes <= 0:
        anio, mes = anio - 1, mes + 12
    return date(anio, mes, 1)


def _usuario(institucion, nombre_usuario, nombre, roles):
    usuario = Usuario(institucion=institucion, nombre_usuario=nombre_usuario, nombre=nombre)
    usuario.set_password(CONTRASENA)
    usuario.save()
    usuario.roles.set(roles)
    return usuario


class Command(BaseCommand):
    help = 'Carga datos de prueba completos en una institución de demostración (por defecto DEMO).'

    def add_arguments(self, parser):
        parser.add_argument('codigo', nargs='?', default='DEMO')

    def handle(self, *args, codigo, **opciones):
        institucion = Institucion.objects.filter(codigo=codigo.strip().upper()).first()
        if institucion is None:
            raise CommandError(f'No existe la institución {codigo}. Las de demostración se crean con install.bat.')
        if not institucion.codigo.startswith('DEMO'):
            raise CommandError('Solo se cargan datos de prueba en instituciones de demostración (código DEMO…).')
        if Conexion.objects.de(institucion).exists():
            if not Conexion.objects.de(institucion).filter(Code='CX-0001').exists():
                raise CommandError(f'{institucion.codigo} ya tiene conexiones: no se cargan datos de prueba encima.')
            with transaction.atomic():
                self._completar(institucion)
            return
        with transaction.atomic():
            self._cargar(institucion)
        self.stdout.write(self.style.SUCCESS(f'\nDatos de prueba cargados en {institucion.codigo}.'))
        self.stdout.write(f'  Usuarios nuevos (contraseña {CONTRASENA}): cobrador1 (toma lecturas) · cajero1 (factura, '
                          f'cobra, caja y gastos).')
        self.stdout.write('  El usuario admin sigue igual.')
        self.stdout.write('  Portal de abonados activo: /portal · pruebe con C.I. 1234567 y maria@ejemplo.com (el PIN '
                          'llega por correo; sin servidor de correo queda en backend/datos/correos/).')

    def _cargar(self, institucion):
        hoy = timezone.localdate()
        meses = [_mes(hoy, 2), _mes(hoy, 1)]          # dos meses ya leídos
        actual = hoy.strftime('%Y-%m')

        # Facturación autoimpresa con numeración (la habilitación real la define la plataforma).
        institucion.modalidad_facturacion = 'autoimpresa'
        institucion.ruc = institucion.ruc or '80000000-0'
        institucion.direccion = institucion.direccion or 'Calle Principal 100, San Lorenzo'
        institucion.telefono = institucion.telefono or '021 000 000'
        institucion.portal_abonados = True
        institucion.save()
        punto = numeracion.crear_punto(institucion=institucion, datos={
            'Code': 'CENTRAL', 'establecimiento': '001', 'punto': '001', 'nombre': 'Oficina central'})
        numeracion.crear_rango(institucion=institucion, datos={
            'Code': 'FAC-PRUEBA', 'punto': punto, 'tipo_documento': 'factura', 'timbrado': '12345678', 'desde': 1,
            'hasta': 9999, 'vigencia_desde': date(hoy.year, 1, 1), 'vigencia_hasta': date(hoy.year + 1, 12, 31)})
        self.stdout.write('  Facturación autoimpresa · punto 001-001 · timbrado 12345678 (de prueba)')

        tarifa = tarifas.crear_tarifa(institucion=institucion, datos={'Code': 'RES', 'nombre': 'Residencial'})
        tarifas.crear_version(tarifa, vigente_desde=meses[0].strftime('%Y-%m'), conceptos=TARIFA,
                              observaciones='Tarifa de prueba')
        self.stdout.write('  Tarifa Residencial: mínimo 10 m³ × 2.500 + excedente 3.000/m³ + ERSSAN 2 % (+ IVA 10 %)')

        zona = Zona.objects.create(institucion=institucion, Code='CENTRO', nombre='Centro', color='#EA284E')
        barrios = [Barrio.objects.create(institucion=institucion, zona=zona, Code=code, nombre=nombre)
                   for code, nombre in (('SAN-JUAN', 'San Juan'), ('VILLA-AURELIA', 'Villa Aurelia'))]

        rol_cobrador = Rol.objects.get(institucion=institucion, Code='COBRADOR')
        rol_cajero, _ = Rol.objects.get_or_create(institucion=institucion, Code='CAJERO', defaults={
            'nombre': 'Cajero', 'descripcion': 'Factura, cobra, maneja su caja y registra gastos (prueba).'})
        rol_cajero.permisos.set(Permiso.objects.filter(codigo__in=[
            'padron.consultar', 'facturacion.emitir', 'facturacion.consultar', 'cobranzas.registrar',
            'cobranzas.consultar', 'caja.operar', 'gastos.registrar', 'gastos.consultar', 'liquidaciones.consultar']))
        cobrador = _usuario(institucion, 'cobrador1', 'Cobrador de prueba', [rol_cobrador])
        _usuario(institucion, 'cajero1', 'Cajero de prueba', [rol_cajero])

        instalacion = _mes(hoy, 3)
        conexiones = []
        for n, (nombre, direccion, documento) in enumerate(CLIENTES, start=1):
            correo = f'{nombre.split()[0].lower().replace("í", "i").replace("ú", "u")}@ejemplo.com' if documento else ''
            cliente = padron.crear_cliente(institucion=institucion, datos={
                'Code': f'C-{n:04d}', 'nombre': nombre, 'documento': documento, 'direccion_referencia': direccion,
                'correo': correo})
            lat = Decimal('-25.340000') + Decimal(n) * Decimal('0.000700')
            lng = Decimal('-57.510000') - Decimal(n % 4) * Decimal('0.000900')
            conexion = padron.crear_conexion(institucion=institucion, datos={
                'Code': f'CX-{n:04d}', 'cliente': cliente, 'direccion': direccion, 'barrio': barrios[n % 2],
                'latitud': lat, 'longitud': lng, 'metodo_ubicacion': 'mapa', 'estado': 'activa',
                'fecha_instalacion': instalacion})
            medidor = padron.crear_medidor(institucion=institucion, datos={
                'Code': f'M-{n:04d}', 'numero': f'A{23040 + n * 17}X', 'marca': 'Prueba'})
            padron.instalar_medidor(conexion, medidor, fecha=instalacion, lectura_inicial=Decimal(100 * n))
            conexiones.append((conexion, medidor, lat, lng))
        self.stdout.write(f'  {len(conexiones)} clientes con su conexión ubicada y su medidor (zona Centro)')

        acumulado = [Decimal(100 * n) for n in range(1, len(conexiones) + 1)]
        for indice, mes in enumerate(meses):
            periodo = mes.strftime('%Y-%m')
            recorrido = recorridos.crear_recorrido(institucion=institucion, datos={
                'Code': f'R-{periodo}', 'nombre': f'Centro {periodo}', 'periodo': periodo})
            recorridos.agregar_conexiones(recorrido, conexiones=[c[0] for c in conexiones])
            recorridos.asignar_cobrador(recorrido, cobrador)
            recorridos.cambiar_estado(recorrido, 'abierto')
            momento = timezone.make_aware(datetime.combine(mes + timedelta(days=14), time(9, 30)))
            for n, (conexion, medidor, lat, lng) in enumerate(conexiones):
                acumulado[n] += CONSUMOS[n][indice]
                lecturas.registrar_lectura(institucion=institucion, usuario=cobrador, datos={
                    'id_operacion': uuid.uuid4(), 'recorrido': recorrido.Code, 'medidor': medidor.Code,
                    'lectura_actual': acumulado[n], 'capturada_en': momento + timedelta(minutes=12 * n),
                    'latitud': lat, 'longitud': lng, 'comentario': ''},
                    foto=SimpleUploadedFile('medidor.png', FOTO, content_type='image/png'))
            recorridos.cambiar_estado(recorrido, 'cerrado')
            self.stdout.write(f'  Recorrido {recorrido.Code}: leído y cerrado (liquidaciones listas para facturar)')

        recorrido = recorridos.crear_recorrido(institucion=institucion, datos={
            'Code': f'R-{actual}', 'nombre': f'Centro {actual}', 'periodo': actual})
        recorridos.agregar_conexiones(recorrido, conexiones=[c[0] for c in conexiones])
        recorridos.asignar_cobrador(recorrido, cobrador)
        recorridos.cambiar_estado(recorrido, 'abierto')
        self.stdout.write(f'  Recorrido {recorrido.Code}: abierto y asignado a cobrador1 (para tomar lecturas con '
                          f'el celular; los medidores son M-0001 … M-0008, con su número A23057X, A23074X…)')
        self._otra_institucion(institucion)

    def _completar(self, institucion):
        """Datos cargados con una versión anterior: completa solo lo que falta, sin crear lecturas ni facturas."""
        from apps.padron.models import Cliente, Medidor
        cambios = []
        if not institucion.portal_abonados:
            institucion.portal_abonados = True
            institucion.save(update_fields=['portal_abonados'])
            cambios.append('portal de abonados activado')
        n_correos = 0
        for n, (nombre, _direccion, documento) in enumerate(CLIENTES, start=1):
            cliente = Cliente.objects.de(institucion).filter(Code=f'C-{n:04d}', correo='').first()
            if cliente is not None and documento:
                cliente.correo = f'{nombre.split()[0].lower().replace("í", "i").replace("ú", "u")}@ejemplo.com'
                cliente.save()
                n_correos += 1
        if n_correos:
            cambios.append(f'{n_correos} clientes con correo')
        n_numeros = 0
        for n in range(1, len(CLIENTES) + 1):
            medidor = Medidor.objects.de(institucion).filter(Code=f'M-{n:04d}', numero='').first()
            numero = f'A{23040 + n * 17}X'
            if medidor is not None and not Medidor.objects.de(institucion).filter(numero=numero).exists():
                padron.actualizar_medidor(medidor, {'numero': numero})
                n_numeros += 1
        if n_numeros:
            cambios.append(f'{n_numeros} medidores con número')
        admin = Usuario.objects.filter(institucion=institucion, nombre_usuario='admin', correo='').first()
        if admin is not None:
            admin.correo = 'admin@ejemplo.com'
            admin.save(update_fields=['correo'])
            cambios.append('admin con correo admin@ejemplo.com (para probar «¿Olvidó su contraseña?»)')
        self._otra_institucion(institucion)
        self.stdout.write(self.style.SUCCESS(
            f'{institucion.codigo} ya tenía datos de prueba: ' + ('; '.join(cambios) if cambios else 'no faltaba nada') + '.'))

    def _otra_institucion(self, institucion):
        """La misma persona (María Benítez, C.I. 1234567) también es cliente de DEMO2: el portal muestra las dos."""
        otra = Institucion.objects.filter(codigo='DEMO2').exclude(pk=institucion.pk).first()
        if otra is None or Conexion.objects.de(otra).exists():
            return
        otra.portal_abonados = True
        otra.save(update_fields=['portal_abonados'])
        cliente = padron.crear_cliente(institucion=otra, datos={
            'Code': 'ABO-001', 'nombre': 'María Benítez', 'documento': '1234567-8', 'correo': 'maria@ejemplo.com'})
        padron.crear_conexion(institucion=otra, datos={
            'Code': 'CASA-QUINTA', 'cliente': cliente, 'direccion': 'Compañía Ytororó km 3', 'estado': 'activa',
            'latitud': Decimal('-25.420000'), 'longitud': Decimal('-57.450000'), 'metodo_ubicacion': 'mapa'})
        self.stdout.write('  DEMO2: María Benítez (C.I. 1234567) también es cliente aquí (portal en las dos)')
