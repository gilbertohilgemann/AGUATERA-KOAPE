"""Alta de instituciones, cambios de estado y panel de la plataforma."""
from django.test import TestCase

from apps.auditoria.models import RegistroAuditoria
from apps.identidad.models import Rol, Usuario
from apps.plataforma.models import Institucion
from apps.plataforma.servicios import cambiar_estado, crear_institucion
from comun.errores import ErrorNegocio
from comun.pruebas.utilidades import CONTRASENA, LimpiarLimites, admin_de, cliente_de, nueva_institucion


class InstitucionesTests(LimpiarLimites, TestCase):
    def test_alta_crea_administrador_roles_y_auditoria(self):
        inst = nueva_institucion('junta-sl')
        self.assertEqual(inst.codigo, 'JUNTA-SL')
        admin = Usuario.objects.get(institucion=inst)
        self.assertTrue(admin.es_admin_institucion)
        self.assertTrue(admin.debe_cambiar_contrasena)
        self.assertFalse(admin.is_staff)
        self.assertEqual(set(Rol.objects.de(inst).values_list('nombre', flat=True)), {'Cobrador', 'Consulta'})
        self.assertTrue(RegistroAuditoria.objects.filter(accion='institucion_creada', institucion=inst).exists())

    def test_alta_es_todo_o_nada(self):
        with self.assertRaises(Exception):
            crear_institucion(datos={'codigo': 'X', 'nombre': 'Código inválido'}, admin_usuario='admin',
                              admin_contrasena=CONTRASENA)
        self.assertFalse(Institucion.objects.exists())
        self.assertFalse(Usuario.objects.exists())

    def test_cambio_de_estado_exige_motivo_y_transicion_valida(self):
        inst = nueva_institucion('JUNTA-SL')
        with self.assertRaises(ErrorNegocio):
            cambiar_estado(inst, 'suspendida', motivo='  ')
        with self.assertRaises(ErrorNegocio):
            cambiar_estado(inst, 'activa', motivo='ya está activa')
        cambiar_estado(inst, 'archivada', motivo='Dejó de usar el sistema')
        inst.refresh_from_db()
        self.assertEqual(inst.estado, 'archivada')
        registro = RegistroAuditoria.objects.get(accion='institucion_estado')
        self.assertEqual(registro.motivo, 'Dejó de usar el sistema')
        self.assertEqual((registro.antes, registro.despues), ({'estado': 'activa'}, {'estado': 'archivada'}))

    def test_la_institucion_no_cambia_su_codigo_ni_su_modalidad_fiscal(self):
        inst = nueva_institucion('JUNTA-SL')
        admin_de(inst)
        cliente = cliente_de(inst)
        r = cliente.patch('/api/v1/institucion/', {'codigo': 'OTRO', 'modalidad_facturacion': 'autoimpresa',
                                                   'telefono': '0981 123456'}, format='json')
        self.assertEqual(r.status_code, 200)
        inst.refresh_from_db()
        self.assertEqual((inst.codigo, inst.modalidad_facturacion, inst.telefono),
                         ('JUNTA-SL', 'no_configurada', '0981 123456'))
        registro = RegistroAuditoria.objects.get(accion='institucion_modificada')
        self.assertEqual((registro.antes['telefono'], registro.despues['telefono']), ('', '0981 123456'))


class PanelPlataformaTests(TestCase):
    def setUp(self):
        self.root = Usuario.objects.create_superuser(identificador='root', password=CONTRASENA)
        self.client.force_login(self.root)

    def test_alta_desde_el_panel(self):
        r = self.client.post('/admin/plataforma/institucion/add/', {
            'codigo': 'aguatera-1', 'nombre': 'Aguatera Uno', 'zona_horaria': 'America/Asuncion',
            'configuracion_regional': 'es-PY', 'admin_usuario': 'jefe', 'admin_contrasena': 'Inicial.Segura.2026',
        })
        self.assertEqual(r.status_code, 302, r.content[:2000])
        inst = Institucion.objects.get(codigo='AGUATERA-1')
        self.assertTrue(Usuario.objects.get(institucion=inst, nombre_usuario='jefe').es_admin_institucion)

    def test_cambiar_estado_desde_el_panel(self):
        inst = nueva_institucion('JUNTA-SL')
        r = self.client.post(f'/admin/plataforma/institucion/{inst.pk}/estado/', {'estado': 'suspendida', 'motivo': 'Prueba'})
        self.assertEqual(r.status_code, 302)
        inst.refresh_from_db()
        self.assertEqual(inst.estado, 'suspendida')

    def test_paneles_sin_tabla_y_listados_abren(self):
        nueva_institucion('JUNTA-SL')
        for url in ('/admin/', '/admin/plataforma/institucion/', '/admin/identidad/usuario/', '/admin/auditoria/registroauditoria/',
                    '/admin/migracion_bd/migracionbasedatos/', '/admin/respaldo/respaldo/', '/admin/manual/manualplataforma/'):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_restablecer_contrasena_de_un_admin_institucional_desde_el_panel(self):
        inst = nueva_institucion('JUNTA-SL')
        admin = admin_de(inst)
        r = self.client.post(f'/admin/identidad/usuario/{admin.pk}/password/',
                             {'password1': 'Restablecida.2026', 'password2': 'Restablecida.2026'})
        self.assertEqual(r.status_code, 302)
        admin.refresh_from_db()
        self.assertTrue(admin.check_password('Restablecida.2026'))
        self.assertTrue(admin.debe_cambiar_contrasena)
        self.assertTrue(RegistroAuditoria.objects.filter(accion='contrasena_restablecida_por_plataforma').exists())

    def test_un_usuario_de_institucion_no_entra_al_panel(self):
        inst = nueva_institucion('JUNTA-SL')
        self.client.logout()
        r = self.client.post('/admin/login/?next=/admin/', {'username': 'JUNTA-SL/admin', 'password': CONTRASENA})
        self.assertEqual(r.status_code, 200)  # vuelve al formulario: no es personal de la plataforma
        self.assertFalse(r.wsgi_request.user.is_authenticated)
        del inst
