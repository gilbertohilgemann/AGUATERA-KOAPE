"""La auditoría es de solo inserción."""
from django.test import TestCase

from apps.auditoria.models import AuditoriaInmutable, RegistroAuditoria
from apps.auditoria.servicios import registrar


class AuditoriaInmutableTests(TestCase):
    def setUp(self):
        self.registro = registrar('prueba', usuario_nombre='sistema', entidad='x', entidad_id=1,
                                  contrasena='no-guardar', token='tampoco', dato='sí',
                                  despues={'clave': 'oculta', 'campo': 'visible'})

    def test_no_guarda_secretos(self):
        self.assertEqual(self.registro.detalle, {'dato': 'sí'})
        self.assertEqual(self.registro.despues, {'campo': 'visible'})

    def test_no_se_modifica_ni_se_borra(self):
        self.registro.accion = 'otra'
        with self.assertRaises(AuditoriaInmutable):
            self.registro.save()
        with self.assertRaises(AuditoriaInmutable):
            self.registro.delete()
        with self.assertRaises(AuditoriaInmutable):
            RegistroAuditoria.objects.filter(pk=self.registro.pk).update(accion='otra')
        with self.assertRaises(AuditoriaInmutable):
            RegistroAuditoria.objects.all().delete()
        self.assertEqual(RegistroAuditoria.objects.get().accion, 'prueba')

    def test_guarda_id_de_solicitud_e_ip(self):
        from django.test import RequestFactory
        request = RequestFactory().get('/', REMOTE_ADDR='10.0.0.5')
        request.id_solicitud = 'abc12345'
        registro = registrar('prueba2', request=request, usuario_nombre='sistema')
        self.assertEqual((registro.ip, registro.id_solicitud), ('10.0.0.5', 'abc12345'))

    def test_la_respuesta_trae_el_id_de_solicitud(self):
        r = self.client.get('/api/v1/salud/', HTTP_X_ID_SOLICITUD='pedido-0001')
        self.assertEqual(r['X-Id-Solicitud'], 'pedido-0001')
        r = self.client.get('/api/v1/salud/', HTTP_X_ID_SOLICITUD='mal formado!')
        self.assertEqual(len(r['X-Id-Solicitud']), 32)
