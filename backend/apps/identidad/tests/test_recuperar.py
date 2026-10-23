"""Recuperar la contraseña por correo (sección 5.2, D51)."""
import re

from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.identidad.models import TokenSesion, Usuario
from comun.pruebas.utilidades import CONTRASENA, LimpiarLimites, admin_de, cliente_de, nueva_institucion

NUEVA = 'Otra.Clave.Segura.2026'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RecuperarTests(LimpiarLimites, TestCase):
    def setUp(self):
        super().setUp()
        self.inst = nueva_institucion('JUNTA-R')
        self.admin = admin_de(self.inst)
        Usuario.objects.filter(pk=self.admin.pk).update(correo='admin@junta.com')
        self.web = APIClient()

    def pedir(self, codigo='JUNTA-R', usuario='admin'):
        r = self.web.post('/api/v1/auth/recuperar/', {'codigo_institucion': codigo, 'usuario': usuario}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        return r.data['detalle']

    def confirmar(self, codigo, nueva=NUEVA, estado=200, usuario='admin'):
        r = self.web.post('/api/v1/auth/recuperar/confirmar/', {
            'codigo_institucion': 'junta-r', 'usuario': usuario, 'codigo': codigo, 'contrasena_nueva': nueva},
            format='json')
        self.assertEqual(r.status_code, estado, r.data)
        return r.data

    def codigo(self):
        return re.search(r'\b(\d{6})\b', mail.outbox[-1].body).group(1)

    def test_el_codigo_llega_al_correo_y_permite_elegir_otra_contrasena(self):
        sesion = cliente_de(self.inst)
        mensaje = self.pedir()
        self.assertEqual(mail.outbox[-1].to, ['admin@junta.com'])
        codigo = self.codigo()
        self.assertNotIn(codigo, Usuario.objects.get(pk=self.admin.pk).recuperacion_codigo)   # solo el hash
        self.confirmar(codigo, nueva='123', estado=400)                                      # contraseña débil
        self.confirmar(codigo)
        self.assertEqual(sesion.get('/api/v1/auth/yo/').status_code, 401)                    # sesiones cerradas
        self.assertFalse(TokenSesion.objects.filter(usuario=self.admin, revocado_en__isnull=True).exists())
        cliente_de(self.inst, contrasena=NUEVA)
        self.assertEqual(self.confirmar(codigo, estado=400)['codigo'], 'codigo_invalido')    # un solo uso
        self.assertIn('código', mensaje)

    def test_misma_respuesta_si_no_existe_o_no_tiene_correo(self):
        respuesta = self.pedir()
        mail.outbox.clear()
        self.assertEqual(self.pedir(usuario='nadie'), respuesta)
        self.assertEqual(self.pedir(codigo='NO-EXISTE'), respuesta)
        Usuario.objects.filter(pk=self.admin.pk).update(correo='', recuperacion_enviada_en=None)
        self.assertEqual(self.pedir(), respuesta)
        self.assertEqual(len(mail.outbox), 0)

    def test_espera_entre_pedidos_e_intentos_limitados(self):
        self.pedir()
        self.pedir()                                    # con un código vigente no se manda otro (ni se anula)
        self.assertEqual(len(mail.outbox), 1)
        codigo = self.codigo()
        malo = '000000' if codigo != '000000' else '111111'
        for _ in range(5):
            self.confirmar(malo, estado=400)
        self.confirmar(codigo, estado=400)              # tras 5 errores el código ya no sirve
        self.pedir()                                    # y en 24 horas no se mandan más (no se prueba sin fin)
        self.assertEqual(len(mail.outbox), 1)
        cliente_de(self.inst, contrasena=CONTRASENA)    # la contraseña anterior sigue igual

    def test_cambiar_el_correo_o_restablecer_anula_el_codigo_pendiente(self):
        otro = Usuario.objects.create_user(institucion=self.inst, nombre_usuario='cajero', password=CONTRASENA,
                                           correo='cajero@junta.com')
        api = cliente_de(self.inst)
        self.pedir(usuario='cajero')
        codigo = self.codigo()
        r = api.patch(f'/api/v1/usuarios/{otro.pk}/', {'correo': 'nuevo@junta.com'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.confirmar(codigo, usuario='cajero', estado=400)['codigo'], 'codigo_invalido')
        Usuario.objects.filter(pk=otro.pk).update(recuperacion_enviada_en=None)
        self.pedir(usuario='cajero')
        codigo = self.codigo()
        r = api.post(f'/api/v1/usuarios/{otro.pk}/restablecer-contrasena/', {'contrasena_nueva': NUEVA + 'x'},
                     format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.confirmar(codigo, usuario='cajero', estado=400)['codigo'], 'codigo_invalido')

    def test_desbloquea_al_usuario(self):
        for _ in range(6):
            self.web.post('/api/v1/auth/ingresar/', {'codigo_institucion': 'JUNTA-R', 'usuario': 'admin',
                                                     'contrasena': 'mal'}, format='json')
        self.assertIsNotNone(Usuario.objects.get(pk=self.admin.pk).bloqueado_hasta)
        self.pedir()
        self.confirmar(self.codigo())
        cliente_de(self.inst, contrasena=NUEVA)
