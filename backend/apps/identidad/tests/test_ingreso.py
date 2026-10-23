"""Ingreso con código institucional, bloqueo por intentos, sesiones y cambio de contraseña."""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.auditoria.models import RegistroAuditoria
from apps.identidad.models import TokenSesion, Usuario
from apps.plataforma.servicios import cambiar_estado
from comun.pruebas.utilidades import CONTRASENA, LimpiarLimites, admin_de, cliente_de, nueva_institucion

URL = '/api/v1/auth/ingresar/'
MENSAJE = 'Datos de ingreso incorrectos o usuario bloqueado temporalmente.'


class IngresoTests(LimpiarLimites, TestCase):
    def setUp(self):
        super().setUp()
        self.inst = nueva_institucion('JUNTA-SL')
        self.cliente = APIClient()

    def ingresar(self, codigo='JUNTA-SL', usuario='admin', contrasena=CONTRASENA, **extra):
        return self.cliente.post(URL, {'codigo_institucion': codigo, 'usuario': usuario, 'contrasena': contrasena,
                                       **extra}, format='json')

    def test_ingreso_correcto_devuelve_token_institucion_y_permisos(self):
        r = self.ingresar(codigo='junta-sl', usuario='ADMIN')  # sin distinguir mayúsculas
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['token'])
        self.assertEqual(r.data['institucion']['codigo'], 'JUNTA-SL')
        self.assertIn('usuarios.administrar', r.data['permisos'])
        self.assertTrue(r.data['usuario']['debe_cambiar_contrasena'])  # contraseña inicial
        token = TokenSesion.objects.get()
        self.assertNotEqual(token.clave_hash, r.data['token'])  # solo se guarda el hash
        self.assertTrue(RegistroAuditoria.objects.filter(accion='ingreso', institucion=self.inst).exists())

    def test_errores_de_credenciales_dan_siempre_el_mismo_mensaje(self):
        for datos in ({'codigo': 'NO-EXISTE'}, {'usuario': 'nadie'}, {'contrasena': 'incorrecta'}):
            r = self.ingresar(**datos)
            self.assertEqual(r.status_code, 400)
            self.assertEqual(r.data['detalle'], MENSAJE)
        self.assertEqual(RegistroAuditoria.objects.filter(accion='ingreso_fallido').count(), 3)

    def test_la_auditoria_de_ingreso_no_guarda_la_contrasena(self):
        self.ingresar(contrasena='Secreta.Que.No.Debe.Verse')
        for registro in RegistroAuditoria.objects.all():
            self.assertNotIn('Secreta.Que.No.Debe.Verse', str(registro.detalle) + registro.motivo)

    @override_settings(KOAPE={'VIGENCIA_TOKEN_HORAS': 12, 'INTENTOS_INGRESO_MAXIMOS': 3, 'MINUTOS_BLOQUEO_INGRESO': 15})
    def test_bloqueo_tras_intentos_fallidos(self):
        for _ in range(3):
            self.ingresar(contrasena='mal')
        r = self.ingresar()  # contraseña correcta, pero bloqueado
        self.assertEqual(r.status_code, 400)
        usuario = Usuario.objects.get(institucion=self.inst, nombre_usuario='admin')
        self.assertIsNotNone(usuario.bloqueado_hasta)
        usuario.bloqueado_hasta = timezone.now() - timedelta(minutes=1)
        usuario.save()
        self.assertEqual(self.ingresar().status_code, 200)

    def test_usuario_desactivado_no_ingresa(self):
        Usuario.objects.filter(institucion=self.inst).update(is_active=False)
        self.assertEqual(self.ingresar().status_code, 400)

    def test_institucion_suspendida_no_ingresa_y_se_cierran_sus_sesiones(self):
        admin_de(self.inst)
        cliente = cliente_de(self.inst)
        self.assertEqual(cliente.get('/api/v1/auth/yo/').status_code, 200)
        cambiar_estado(self.inst, 'suspendida', motivo='Falta de pago')
        self.assertEqual(cliente.get('/api/v1/auth/yo/').status_code, 401)
        r = self.ingresar()
        self.assertEqual(r.status_code, 403)
        self.assertIn('suspendida', r.data['detalle'])

    def test_honeypot_responde_como_credenciales_incorrectas(self):
        r = self.ingresar(sitio_web='http://spam')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data['detalle'], MENSAJE)
        self.assertFalse(TokenSesion.objects.exists())

    def test_los_usuarios_de_la_plataforma_no_ingresan_por_la_api(self):
        plataforma = Usuario.objects.create_superuser(identificador='root', password=CONTRASENA)
        self.assertIsNone(plataforma.institucion)
        self.assertEqual(self.ingresar(usuario='root').status_code, 400)

    def test_token_vencido_o_revocado(self):
        admin_de(self.inst)
        cliente = cliente_de(self.inst)
        TokenSesion.objects.update(expira_en=timezone.now() - timedelta(seconds=1))
        self.assertEqual(cliente.get('/api/v1/auth/yo/').status_code, 401)
        cliente = cliente_de(self.inst)
        self.assertEqual(cliente.post('/api/v1/auth/salir/').status_code, 204)
        self.assertEqual(cliente.get('/api/v1/auth/yo/').status_code, 401)

    def test_limite_de_intentos_por_ip(self):
        respuestas = [self.ingresar(contrasena='mal').status_code for _ in range(12)]
        self.assertIn(429, respuestas)


class CambioContrasenaTests(LimpiarLimites, TestCase):
    def setUp(self):
        super().setUp()
        self.inst = nueva_institucion('JUNTA-SL')
        self.cliente = cliente_de(self.inst)  # el admin todavía debe cambiar la contraseña inicial

    def test_con_contrasena_inicial_solo_puede_cambiarla(self):
        self.assertEqual(self.cliente.get('/api/v1/auth/yo/').status_code, 200)
        r = self.cliente.get('/api/v1/usuarios/')
        self.assertEqual(r.status_code, 403)
        self.assertIn('cambiar su contraseña', r.data['detalle'])
        r = self.cliente.post('/api/v1/auth/cambiar-contrasena/', {
            'contrasena_actual': CONTRASENA, 'contrasena_nueva': 'Nueva.Clave.Segura.9'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.cliente.get('/api/v1/usuarios/').status_code, 200)

    def test_rechaza_contrasena_debil_o_actual_incorrecta(self):
        r = self.cliente.post('/api/v1/auth/cambiar-contrasena/', {
            'contrasena_actual': CONTRASENA, 'contrasena_nueva': '1234'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.cliente.post('/api/v1/auth/cambiar-contrasena/', {
            'contrasena_actual': 'otra', 'contrasena_nueva': 'Nueva.Clave.Segura.9'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_cambiar_contrasena_cierra_las_otras_sesiones(self):
        otra = cliente_de(self.inst)
        self.cliente.post('/api/v1/auth/cambiar-contrasena/', {
            'contrasena_actual': CONTRASENA, 'contrasena_nueva': 'Nueva.Clave.Segura.9'}, format='json')
        self.assertEqual(otra.get('/api/v1/auth/yo/').status_code, 401)
        self.assertEqual(self.cliente.get('/api/v1/auth/yo/').status_code, 200)
