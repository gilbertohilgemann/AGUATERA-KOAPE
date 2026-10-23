"""
Criterio de aceptación de la Fase 1 (y prueba obligatoria 1 de la sección 21):
dos instituciones operan en el mismo sistema sin acceder a los datos de la otra,
aunque el usuario conozca los identificadores de la otra institución.
"""
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.auditoria.models import RegistroAuditoria
from apps.identidad.models import Rol, Usuario
from comun.errores import ErrorCruceInstitucion
from comun.modelos import validar_misma_institucion

from .utilidades import CONTRASENA, LimpiarLimites, admin_de, cliente_de, nueva_institucion


class AislamientoEntreInstitucionesTests(LimpiarLimites, TestCase):
    def setUp(self):
        super().setUp()
        self.a = nueva_institucion('JUNTA-A')
        self.b = nueva_institucion('JUNTA-B')
        admin_de(self.a)
        admin_de(self.b)
        self.cliente_a = cliente_de(self.a)
        self.usuario_b = Usuario.objects.get(institucion=self.b, nombre_usuario='admin')
        self.rol_b = Rol.objects.get(institucion=self.b, nombre='Cobrador')

    def test_el_mismo_nombre_de_usuario_existe_en_las_dos_instituciones(self):
        self.assertEqual(Usuario.objects.filter(nombre_usuario='admin', institucion__isnull=False).count(), 2)
        self.assertEqual(admin_de(self.a).identificador, 'JUNTA-A/admin')
        self.assertEqual(admin_de(self.b).identificador, 'JUNTA-B/admin')

    def test_la_lista_de_usuarios_solo_trae_los_de_la_institucion_de_la_sesion(self):
        respuesta = self.cliente_a.get('/api/v1/usuarios/')
        self.assertEqual(respuesta.status_code, 200)
        ids = {u['id'] for u in respuesta.data['results']}
        self.assertNotIn(self.usuario_b.pk, ids)
        self.assertEqual(ids, set(Usuario.objects.filter(institucion=self.a).values_list('pk', flat=True)))

    def test_un_id_de_otra_institucion_responde_no_existe(self):
        self.assertEqual(self.cliente_a.get(f'/api/v1/usuarios/{self.usuario_b.pk}/').status_code, 404)
        self.assertEqual(self.cliente_a.get(f'/api/v1/roles/{self.rol_b.pk}/').status_code, 404)

    def test_no_se_puede_modificar_un_registro_de_otra_institucion(self):
        respuesta = self.cliente_a.patch(f'/api/v1/usuarios/{self.usuario_b.pk}/', {'nombre': 'Intruso'}, format='json')
        self.assertEqual(respuesta.status_code, 404)
        respuesta = self.cliente_a.post(f'/api/v1/usuarios/{self.usuario_b.pk}/restablecer-contrasena/',
                                        {'contrasena_nueva': 'Otra.Clave.2026'}, format='json')
        self.assertEqual(respuesta.status_code, 404)
        self.usuario_b.refresh_from_db()
        self.assertEqual(self.usuario_b.nombre, '')
        self.assertTrue(self.usuario_b.check_password(CONTRASENA))

    def test_no_se_puede_asignar_un_rol_de_otra_institucion_por_la_api(self):
        respuesta = self.cliente_a.post('/api/v1/usuarios/', {
            'usuario': 'cobrador1', 'contrasena': 'Clave.Nueva.2026', 'roles': [self.rol_b.pk],
        }, format='json')
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('roles', respuesta.data)
        self.assertFalse(Usuario.objects.filter(nombre_usuario='cobrador1').exists())

    def test_la_base_rechaza_un_rol_de_otra_institucion_aunque_una_vista_falle(self):
        usuario_a = admin_de(self.a)
        with self.assertRaises(ErrorCruceInstitucion), transaction.atomic():
            usuario_a.roles.add(self.rol_b)
        with self.assertRaises(ErrorCruceInstitucion), transaction.atomic():
            self.rol_b.usuarios.add(usuario_a)
        self.assertFalse(usuario_a.roles.filter(pk=self.rol_b.pk).exists())

    def test_validar_misma_institucion(self):
        validar_misma_institucion(self.a, admin_de(self.a))
        with self.assertRaises(ErrorCruceInstitucion):
            validar_misma_institucion(self.a, self.rol_b)

    def test_el_navegador_no_puede_elegir_la_institucion(self):
        # Un parámetro o campo «institucion» que mande el navegador se ignora: manda el token.
        respuesta = self.cliente_a.get('/api/v1/usuarios/', {'institucion': self.b.pk})
        self.assertNotIn(self.usuario_b.pk, {u['id'] for u in respuesta.data['results']})
        respuesta = self.cliente_a.post('/api/v1/roles/', {'Code': 'R-Cajero', 'nombre': 'Cajero', 'institucion': self.b.pk}, format='json')
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(Rol.objects.get(pk=respuesta.data['id']).institucion, self.a)
        respuesta = self.cliente_a.get('/api/v1/institucion/', {'codigo': self.b.codigo})
        self.assertEqual(respuesta.data['codigo'], 'JUNTA-A')

    def test_la_auditoria_solo_muestra_la_institucion_de_la_sesion(self):
        cliente_de(self.b)  # genera un ingreso en B
        respuesta = self.cliente_a.get('/api/v1/auditoria/')
        self.assertEqual(respuesta.status_code, 200)
        ids_b = set(RegistroAuditoria.objects.filter(institucion=self.b).values_list('pk', flat=True))
        self.assertTrue(ids_b)
        self.assertFalse(ids_b & {r['id'] for r in respuesta.data['results']})
        un_id_b = next(iter(ids_b))
        self.assertEqual(self.cliente_a.get(f'/api/v1/auditoria/{un_id_b}/').status_code, 404)

    def test_un_usuario_de_a_no_ingresa_con_el_codigo_de_b(self):
        usuario = Usuario(institucion=self.a, nombre_usuario='solo_en_a')
        usuario.set_password(CONTRASENA)
        usuario.save()
        respuesta = self.client.post('/api/v1/auth/ingresar/', {
            'codigo_institucion': 'JUNTA-B', 'usuario': 'solo_en_a', 'contrasena': CONTRASENA,
        }, content_type='application/json')
        self.assertEqual(respuesta.status_code, 400)

    def test_un_usuario_de_institucion_nunca_entra_al_panel_de_la_plataforma(self):
        usuario = admin_de(self.a)
        usuario.is_staff = True
        with self.assertRaises(IntegrityError), transaction.atomic():
            usuario.save()
