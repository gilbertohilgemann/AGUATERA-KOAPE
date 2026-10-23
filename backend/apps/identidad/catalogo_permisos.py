"""
Catálogo de permisos del sistema.

Los códigos están fijos en el código (cada fase agrega los suyos); los roles de cada institución
combinan estos permisos. Después de cada `migrate` se sincroniza la tabla `identidad.Permiso` con
este catálogo: los que ya no figuran quedan como no vigentes (no se borran, los roles los referencian).
"""

PERMISOS = [
    # (código, descripción, módulo)
    ('institucion.ver', 'Ver los datos de la institución', 'Institución'),
    ('institucion.editar', 'Editar los datos de la institución', 'Institución'),
    ('usuarios.administrar', 'Administrar usuarios y sus roles', 'Usuarios y permisos'),
    ('roles.administrar', 'Administrar roles y permisos', 'Usuarios y permisos'),
    ('auditoria.consultar', 'Consultar la auditoría de la institución', 'Auditoría'),
    # Fase 2: padrón y mapa
    ('territorio.gestionar', 'Administrar zonas y barrios (y dibujar sus polígonos)', 'Territorio'),
    ('padron.consultar', 'Consultar clientes, conexiones y medidores', 'Padrón'),
    ('padron.clientes', 'Administrar clientes (titulares)', 'Padrón'),
    ('padron.conexiones', 'Administrar conexiones: ubicación, estado, titular y fotos', 'Padrón'),
    ('padron.medidores', 'Administrar medidores e instalarlos, retirarlos o sustituirlos', 'Padrón'),
    ('mapa.ver', 'Ver el mapa completo de conexiones', 'Mapa'),
    # Convención SerNr: numeración de facturas y notas de crédito
    ('facturacion.numeracion', 'Configurar puntos de expedición y rangos de numeración (SerNr)', 'Facturación'),
    # Fase 3: recorridos y lecturas
    ('recorridos.gestionar', 'Armar recorridos, asignar cobradores, abrirlos y cerrarlos', 'Recorridos y lecturas'),
    ('lecturas.consultar', 'Consultar lecturas, sus fotos y comprobantes', 'Recorridos y lecturas'),
    ('lecturas.registrar', 'Tomar lecturas en los recorridos asignados (aplicación del cobrador)', 'Recorridos y lecturas'),
    ('lecturas.revisar', 'Autorizar excepciones, corregir y anular lecturas', 'Recorridos y lecturas'),
    # Fase 4: tarifas y liquidaciones
    ('tarifas.gestionar', 'Configurar tarifas, sus versiones y conceptos; liquidar lecturas pendientes',
     'Tarifas y liquidaciones'),
    ('liquidaciones.consultar', 'Consultar liquidaciones e importes', 'Tarifas y liquidaciones'),
    # Fase 5: facturación
    ('facturacion.emitir', 'Emitir facturas a los clientes (caja)', 'Facturación'),
    ('facturacion.consultar', 'Consultar facturas y descargar su PDF', 'Facturación'),
    ('facturacion.anular', 'Anular facturas (con motivo)', 'Facturación'),
    # Fase 6: pagos y recibos
    ('cobranzas.registrar', 'Cobrar facturas a crédito y emitir recibos', 'Pagos y recibos'),
    ('cobranzas.consultar', 'Consultar pagos, recibos y saldos de los clientes', 'Pagos y recibos'),
    ('cobranzas.anular', 'Anular recibos (revierte el pago, con motivo)', 'Pagos y recibos'),
    ('cobranzas.formas_pago', 'Configurar las formas de pago', 'Pagos y recibos'),
    # Fase 7: caja y gastos
    ('caja.operar', 'Abrir y cerrar su propia caja (necesario para cobrar)', 'Caja y gastos'),
    ('caja.supervisar', 'Ver todas las cajas, revisar diferencias y administrar las cajas', 'Caja y gastos'),
    ('gastos.consultar', 'Consultar gastos y sus comprobantes', 'Caja y gastos'),
    ('gastos.registrar', 'Registrar gastos, adjuntar comprobantes e imprimir la boleta interna', 'Caja y gastos'),
    ('gastos.confirmar', 'Confirmar gastos (salen de su caja), anularlos y configurar sus categorías',
     'Caja y gastos'),
    # Fase 8: integraciones
    ('integraciones.administrar', 'Crear y revocar credenciales para que otros sistemas consulten la API',
     'Integraciones'),
]

CODIGOS = {p[0] for p in PERMISOS}

# Roles que se crean con cada institución nueva (se pueden editar o desactivar después).
ROLES_INICIALES = [
    # (Code, nombre, descripción, permisos)
    ('COBRADOR', 'Cobrador', 'Toma lecturas en sus recorridos asignados con la aplicación del celular.',
     ['lecturas.registrar']),
    ('CONSULTA', 'Consulta', 'Solo consulta: datos de la institución, padrón, mapa, lecturas, facturas y cobros.',
     ['institucion.ver', 'padron.consultar', 'mapa.ver', 'lecturas.consultar', 'liquidaciones.consultar',
      'facturacion.consultar', 'cobranzas.consultar']),
]


def sincronizar_permisos(alias: str = 'default') -> None:
    from .models import Permiso

    for codigo, descripcion, modulo in PERMISOS:
        Permiso.objects.using(alias).update_or_create(
            codigo=codigo, defaults={'descripcion': descripcion, 'modulo': modulo, 'vigente': True},
        )
    Permiso.objects.using(alias).exclude(codigo__in=CODIGOS).update(vigente=False)


def sincronizar_tras_migrar(sender, using, **kwargs):
    # Los alias temporales del módulo de migración («destino_*») reciben los permisos con loaddata.
    if not using.startswith('destino'):
        sincronizar_permisos(using)
