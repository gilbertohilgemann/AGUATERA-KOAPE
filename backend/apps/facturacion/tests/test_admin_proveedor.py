import json

from django.test import TestCase

from apps.facturacion.admin import ProveedorForm
from apps.facturacion.models import ProveedorFacturacion
from comun.cifrado import descifrar
from comun.pruebas.utilidades import nueva_institucion


class ProveedorAdminTests(TestCase):
    def setUp(self):
        self.institucion = nueva_institucion('PROV')

    def _form(self, credenciales='', instancia=None):
        return ProveedorForm(data={'institucion': self.institucion.pk, 'nombre': 'Proveedor X', 'adaptador': 'x',
                                   'ambiente': 'pruebas', 'activo': True, 'credenciales_nuevas': credenciales},
                             instance=instancia)

    def test_credenciales_se_guardan_cifradas_y_se_conservan(self):
        form = self._form('{"usuario": "u", "clave": "secreta"}')
        self.assertTrue(form.is_valid(), form.errors)
        proveedor = form.save()
        self.assertNotIn('secreta', proveedor.credenciales)
        self.assertEqual(json.loads(descifrar(proveedor.credenciales))['clave'], 'secreta')
        anterior = proveedor.credenciales
        form = self._form('', ProveedorFacturacion.objects.get(pk=proveedor.pk))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().credenciales, anterior)

    def test_json_invalido_rechazado(self):
        self.assertFalse(self._form('no es json').is_valid())
        self.assertFalse(self._form('[1, 2]').is_valid())
