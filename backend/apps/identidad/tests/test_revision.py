"""Casos que encontró la revisión de seguridad (escalada de privilegios, auditoría, nombres, respaldos)."""
import json
import tempfile
import zipfile
from pathlib import Path

from django.test import TestCase, override_settings

from apps.auditoria.models import AuditoriaInmutable, RegistroAuditoria
from apps.auditoria.servicios import ip_cliente, registrar
from apps.identidad.models import Permiso, Rol, Usuario
from apps.respaldo.restauracion import verificar
from comun.pruebas.utilidades import LimpiarLimites, admin_de, cliente_de, nueva_institucion, usuario_con_permisos


class EscaladaDePrivilegiosTests(LimpiarLimites, TestCase):
    def setUp(self):
        super().setUp()
        self.inst = nueva_institucion('JUNTA-SL')
        admin_de(self.inst)
        self.rrhh = usuario_con_permisos(self.inst, 'rrhh', ['usuarios.administrar'])
        self.cliente = cliente_de(self.inst, 'rrhh')
        self.rol_poderoso = Rol.objects.create(institucion=self.inst, Code='PODEROSO', nombre='Poderoso')
        self.rol_poderoso.permisos.set(Permiso.objects.all())

    def test_no_puede_asignarse_un_rol_con_mas_permisos(self):
        r = self.cliente.patch(f'/api/v1/usuarios/{self.rrhh.pk}/', {'roles': [self.rol_poderoso.pk]}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.cliente.get('/api/v1/auth/yo/').data['permisos'], ['usuarios.administrar'])

    def test_no_puede_dar_a_otro_un_rol_con_mas_permisos(self):
        r = self.cliente.post('/api/v1/usuarios/', {'usuario': 'complice', 'contrasena': 'Clave.Nueva.2026',
                                                    'roles': [self.rol_poderoso.pk]}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_no_puede_tocar_ni_restablecer_a_alguien_con_mas_permisos(self):
        jefe = usuario_con_permisos(self.inst, 'jefe', ['usuarios.administrar', 'roles.administrar'])
        self.assertEqual(self.cliente.patch(f'/api/v1/usuarios/{jefe.pk}/', {'activo': False}, format='json').status_code, 400)
        r = self.cliente.post(f'/api/v1/usuarios/{jefe.pk}/restablecer-contrasena/', {'contrasena_nueva': 'Tomada.2026'},
                              format='json')
        self.assertEqual(r.status_code, 403)

    def test_puede_gestionar_a_quien_tiene_menos_permisos(self):
        cobrador = usuario_con_permisos(self.inst, 'cobrador', [])
        # Un rol sin permisos (el «Cobrador» inicial ya trae «lecturas.registrar», que rrhh no tiene).
        cobrador_rol = Rol.objects.create(institucion=self.inst, Code='LECTOR', nombre='Lector')
        r = self.cliente.patch(f'/api/v1/usuarios/{cobrador.pk}/', {'roles': [cobrador_rol.pk]}, format='json')
        self.assertEqual(r.status_code, 200, r.data)

    def test_quien_administra_roles_solo_otorga_permisos_que_tiene(self):
        roles = usuario_con_permisos(self.inst, 'rolero', ['roles.administrar'])
        cliente = cliente_de(self.inst, 'rolero')
        propio = roles.roles.get()
        r = cliente.patch(f'/api/v1/roles/{propio.pk}/', {'permisos': ['roles.administrar', 'auditoria.consultar']}, format='json')
        self.assertEqual(r.status_code, 400)
        r = cliente.post('/api/v1/roles/', {'Code': 'R-Todo', 'nombre': 'Todo', 'permisos': ['usuarios.administrar']}, format='json')
        self.assertEqual(r.status_code, 400)
        r = cliente.post('/api/v1/roles/', {'Code': 'R-Igual', 'nombre': 'Igual', 'permisos': ['roles.administrar']}, format='json')
        self.assertEqual(r.status_code, 201)

    def test_un_rol_con_permiso_retirado_se_puede_volver_a_guardar(self):
        Permiso.objects.create(codigo='viejo.permiso', descripcion='Retirado', modulo='X', vigente=False)
        rol = Rol.objects.create(institucion=self.inst, Code='VIEJO', nombre='Viejo')
        rol.permisos.set(Permiso.objects.filter(codigo__in=['viejo.permiso', 'institucion.ver']))
        admin = cliente_de(self.inst)
        r = admin.patch(f'/api/v1/roles/{rol.pk}/', {'descripcion': 'x', 'permisos': ['viejo.permiso', 'institucion.ver']},
                        format='json')
        self.assertEqual(r.status_code, 200, r.data)
        r = admin.post('/api/v1/roles/', {'Code': 'R-Nuevo', 'nombre': 'Nuevo', 'permisos': ['viejo.permiso']}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_nombre_de_usuario_valido_y_zona_horaria_valida(self):
        admin = cliente_de(self.inst)
        r = admin.post('/api/v1/usuarios/', {'usuario': 'a b/<x>', 'contrasena': 'Clave.Nueva.2026'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(admin.patch('/api/v1/institucion/', {'zona_horaria': 'Marte/Olympus'}, format='json').status_code, 400)

    def test_limite_de_cambio_de_contrasena(self):
        codigos = [self.cliente.post('/api/v1/auth/cambiar-contrasena/', {
            'contrasena_actual': f'mal{i}', 'contrasena_nueva': 'Otra.Clave.2026'}, format='json').status_code for i in range(12)]
        self.assertIn(429, codigos)


class AuditoriaYRespaldoTests(TestCase):
    def test_un_registro_nuevo_con_el_pk_de_otro_no_lo_pisa(self):
        original = registrar('original', usuario_nombre='sistema')
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            RegistroAuditoria(pk=original.pk, accion='falsificado', ocurrido_en=original.ocurrido_en).save()
        self.assertEqual(RegistroAuditoria.objects.get(pk=original.pk).accion, 'original')
        with self.assertRaises(AuditoriaInmutable):
            original.save()

    def test_claves_sensibles_por_parte_del_nombre(self):
        r = registrar('x', usuario_nombre='s', admin_contrasena='a', DB_CONTRASENA='b', contrasena1='c', campo='ok')
        self.assertEqual(r.detalle, {'campo': 'ok'})

    def test_ip_real_detras_del_proxy(self):
        from django.test import RequestFactory
        pedido = RequestFactory().get('/', REMOTE_ADDR='127.0.0.1', HTTP_X_FORWARDED_FOR='6.6.6.6, 200.1.1.1')
        self.assertEqual(ip_cliente(pedido), '127.0.0.1')
        rf = {**__import__('django.conf').conf.settings.REST_FRAMEWORK, 'NUM_PROXIES': 1}
        with override_settings(REST_FRAMEWORK=rf):
            self.assertEqual(ip_cliente(pedido), '200.1.1.1')

    def test_manifiesto_danado_no_rompe_la_verificacion(self):
        with tempfile.TemporaryDirectory() as tmp:
            for contenido in ('{no es json', json.dumps([1, 2])):
                ruta = Path(tmp) / 'r.zip'
                with zipfile.ZipFile(ruta, 'w') as z:
                    z.writestr('manifiesto.json', contenido)
                self.assertIn('manifiesto.json está dañado.', verificar(ruta)['errores'])
