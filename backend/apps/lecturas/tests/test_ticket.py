"""Ticket de lectura para impresora térmica: empresa, cliente, lectura anterior y actual, consumo y aranceles."""
import re

from apps.facturacion.tests.test_facturas import BaseFacturas
from apps.lecturas.models import Lectura
from apps.lecturas.ticket import contenido
from comun.pruebas.utilidades import admin_de, cliente_de, nueva_institucion


def textos(lectura):
    return [' '.join(str(x) for x in r[1:]) for r in contenido(lectura)]


class TicketTests(BaseFacturas):
    def test_trae_empresa_cliente_lecturas_y_aranceles(self):
        nov = self.nov.lectura                                   # la anterior es la de octubre
        lineas = textos(nov)
        oct_ = self.oct.lectura
        for esperado in (self.a.nombre, 'RUC 80012345-6', 'Nombre María', 'N.º de cliente C1', 'Conexión CX1',
                         'LECTURA ANTERIOR', f'N.º {oct_.comprobante}', 'Lectura 115',
                         'LECTURA ACTUAL', f'N.º {nov.comprobante}', 'Lectura 120', 'Consumo 5 m³',
                         'ARANCELES', f'Liquidación {self.nov.numero}', 'TOTAL Gs. 28.000'):
            self.assertTrue(any(esperado in t for t in lineas), f'falta «{esperado}» en {lineas}')
        # La primera lectura del medidor parte de la instalación.
        self.assertTrue(any('Instalación del medidor' in t for t in textos(oct_)))

    def test_pdf_angosto_para_el_cobrador_y_la_oficina(self):
        url = f'/api/v1/cobrador/lecturas/{self.nov.lectura.comprobante}/ticket/'
        for parametro, mm in (('', 58), ('?ancho=80', 80)):
            r = self.cob.get(url + parametro)
            self.assertEqual((r.status_code, r['Content-Type'], r.content[:5]), (200, 'application/pdf', b'%PDF-'))
            ancho = float(re.search(rb'/MediaBox \[ 0 0 ([\d.]+)', r.content).group(1))
            self.assertAlmostEqual(ancho, mm * 72 / 25.4, places=1)            # papel de 58 u 80 mm
        oficina = f'/api/v1/lecturas/{self.nov.lectura.comprobante}/ticket/'
        self.assertEqual(self.api.get(oficina).status_code, 200)
        otra = nueva_institucion('JUNTA-OTRA')
        admin_de(otra)
        self.assertEqual(cliente_de(otra).get(oficina).status_code, 404)        # aislamiento

    def test_en_revision_no_tiene_aranceles_todavia(self):
        lectura = self.nov.lectura
        Lectura.objects.filter(pk=lectura.pk).update(estado=Lectura.Estado.REVISION, motivo_revision='lectura_menor')
        self.nov.estado = 'anulada'
        self.nov.save(update_fields=['estado'])
        lineas = textos(Lectura.objects.get(pk=lectura.pk))
        self.assertTrue(any('los aranceles se calculan cuando la oficina la confirme' in t for t in lineas))
