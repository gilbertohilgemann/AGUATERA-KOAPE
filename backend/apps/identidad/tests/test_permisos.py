"""Permisos verificados en el servidor y administración de usuarios y roles."""
from django.test import TestCase

from apps.auditoria.models import RegistroAuditoria
from apps.identidad.models import Rol, TokenSesion, Usuario
from comun.pruebas.utilidades import CONTRASENA, LimpiarLimites, admin_de, cliente_de, nueva_institucion, usuario_con_permisos


class PermisosTests(LimpiarLimites, TestCase):
    def setUp(self):
        super().setUp()
        self.inst = nueva_institucion('JUNTA-SL')
        admin_de(self.inst)
        self.admin = cliente_de(self.inst)

    def test_sin_permiso_responde_403(self):
        usuario_con_permisos(self.inst, 'consulta', ['institucion.ver'])
        cliente = cliente_de(self.inst, 'consulta')
        self.assertEqual(cliente.get('/api/v1/institucion/').status_code, 200)
        self.assertEqual(cliente.patch('/api/v1/institucion/', {'telefono': '1'}, format='json').status_code, 403)
        self.assertEqual(cliente.get('/api/v1/usuarios/').status_code, 403)
        self.assertEqual(cliente.get('/api/v1/auditoria/').status_code, 403)

    def test_rol_desactivado_pierde_sus_permisos(self):
        usuario = usuario_con_permisos(self.inst, 'auditor', ['auditoria.consultar'])
        cliente = cliente_de(self.inst, 'auditor')
        self.assertEqual(cliente.get('/api/v1/auditoria/').status_code, 200)
        usuario.roles.update(activo=False)
        self.assertEqual(cliente.get('/api/v1/auditoria/').status_code, 403)

    def test_quien_administra_usuarios_no_puede_hacerse_administrador(self):
        usuario = usuario_con_permisos(self.inst, 'rrhh', ['usuarios.administrar'])
        cliente = cliente_de(self.inst, 'rrhh')
        r = cliente.patch(f'/api/v1/usuarios/{usuario.pk}/', {'es_admin_institucion': True}, format='json')
        self.assertEqual(r.status_code, 400)
        r = cliente.post('/api/v1/usuarios/', {'usuario': 'otro', 'contrasena': 'Clave.Nueva.2026',
                                               'es_admin_institucion': True}, format='json')
        self.assertEqual(r.status_code, 400)
        admin = Usuario.objects.get(institucion=self.inst, nombre_usuario='admin')
        r = cliente.patch(f'/api/v1/usuarios/{admin.pk}/', {'activo': False}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_crear_usuario_con_rol_y_auditoria(self):
        cobrador = Rol.objects.get(institucion=self.inst, nombre='Cobrador')
        r = self.admin.post('/api/v1/usuarios/', {'usuario': 'Cobrador1', 'nombre': 'Juan', 'contrasena': 'Clave.Nueva.2026',
                                                  'roles': [cobrador.pk]}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        nuevo = Usuario.objects.get(pk=r.data['id'])
        self.assertEqual(nuevo.nombre_usuario, 'cobrador1')
        self.assertTrue(nuevo.debe_cambiar_contrasena)
        self.assertEqual(list(nuevo.roles.all()), [cobrador])
        registro = RegistroAuditoria.objects.get(accion='usuario_creado')
        self.assertEqual(registro.despues['roles'], ['Cobrador'])
        self.assertNotIn('contrasena', registro.despues)

    def test_no_se_repite_el_nombre_de_usuario_en_la_institucion(self):
        r = self.admin.post('/api/v1/usuarios/', {'usuario': 'ADMIN', 'contrasena': 'Clave.Nueva.2026'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_los_usuarios_no_se_borran_se_desactivan(self):
        usuario = usuario_con_permisos(self.inst, 'temporal', [])
        cliente_de(self.inst, 'temporal')
        self.assertEqual(self.admin.delete(f'/api/v1/usuarios/{usuario.pk}/').status_code, 405)
        r = self.admin.patch(f'/api/v1/usuarios/{usuario.pk}/', {'activo': False}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(TokenSesion.objects.filter(usuario=usuario, revocado_en__isnull=True).exists())
        # El nombre de usuario es su clave visible: no se cambia (la auditoría lo registra con él).
        r = self.admin.patch(f'/api/v1/usuarios/{usuario.pk}/', {'usuario': 'otro_nombre'}, format='json')
        self.assertEqual(r.status_code, 400)
        registro = RegistroAuditoria.objects.get(accion='usuario_modificado')
        self.assertEqual((registro.antes['activo'], registro.despues['activo']), (True, False))

    def test_restablecer_contrasena(self):
        usuario = usuario_con_permisos(self.inst, 'olvido', [])
        r = self.admin.post(f'/api/v1/usuarios/{usuario.pk}/restablecer-contrasena/',
                            {'contrasena_nueva': 'Recuperada.2026'}, format='json')
        self.assertEqual(r.status_code, 200)
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password('Recuperada.2026'))
        self.assertTrue(usuario.debe_cambiar_contrasena)

    def test_roles_con_permisos_y_sin_borrado(self):
        r = self.admin.post('/api/v1/roles/', {'Code': 'R-Cajero', 'nombre': 'Cajero', 'permisos': ['institucion.ver', 'auditoria.consultar']},
                            format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(sorted(r.data['permisos']), ['auditoria.consultar', 'institucion.ver'])
        self.assertEqual(self.admin.post('/api/v1/roles/', {'Code': 'R-OTRO', 'nombre': 'cajero'}, format='json').status_code, 400)
        self.assertEqual(self.admin.post('/api/v1/roles/', {'Code': 'R-X', 'nombre': 'X', 'permisos': ['no.existe']},
                                         format='json').status_code, 400)
        self.assertEqual(self.admin.delete(f'/api/v1/roles/{r.data["id"]}/').status_code, 405)

    def test_catalogo_de_permisos(self):
        r = self.admin.get('/api/v1/permisos/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('usuarios.administrar', {p['codigo'] for p in r.data})
