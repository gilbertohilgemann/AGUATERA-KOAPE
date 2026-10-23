"""Alta de instituciones y cambios de estado (los usa el panel de la plataforma y los comandos)."""
from django.db import transaction

from apps.auditoria.servicios import registrar
from comun.errores import ErrorNegocio

from .models import Institucion

TRANSICIONES = {
    Institucion.Estado.ACTIVA: {Institucion.Estado.SUSPENDIDA, Institucion.Estado.ARCHIVADA},
    Institucion.Estado.SUSPENDIDA: {Institucion.Estado.ACTIVA, Institucion.Estado.ARCHIVADA},
    Institucion.Estado.ARCHIVADA: {Institucion.Estado.ACTIVA},
}


def foto_institucion(institucion) -> dict:
    return {
        'codigo': institucion.codigo, 'nombre': institucion.nombre, 'ruc': institucion.ruc,
        'direccion': institucion.direccion, 'telefono': institucion.telefono, 'correo': institucion.correo,
        'contacto': institucion.contacto, 'estado': institucion.estado, 'zona_horaria': institucion.zona_horaria,
        'configuracion_regional': institucion.configuracion_regional,
        'modalidad_facturacion': institucion.modalidad_facturacion,
        'lecturas_permite_galeria': institucion.lecturas_permite_galeria,
        'dias_vencimiento_credito': institucion.dias_vencimiento_credito,
        'aplicacion_pagos': institucion.aplicacion_pagos,
        'portal_abonados': institucion.portal_abonados,
    }


@transaction.atomic
def crear_institucion(*, datos: dict, admin_usuario: str, admin_contrasena: str, actor=None, request=None,
                      admin_nombre: str = '', admin_correo: str = '') -> Institucion:
    """
    Crea la institución, su administrador inicial (deberá cambiar la contraseña al primer ingreso)
    y los roles iniciales. Todo o nada: si algo falla, no queda nada a medio crear.
    """
    from apps.identidad.catalogo_permisos import ROLES_INICIALES
    from apps.identidad.models import Permiso, Rol, Usuario

    datos = {**datos, 'codigo': (datos.get('codigo') or '').strip().upper()}
    institucion = Institucion(**datos)
    institucion.full_clean()
    institucion.save()
    administrador = Usuario(
        institucion=institucion, nombre_usuario=admin_usuario, nombre=admin_nombre, correo=admin_correo,
        es_admin_institucion=True, debe_cambiar_contrasena=True,
    )
    administrador.set_password(admin_contrasena)
    administrador.save()
    for code, nombre, descripcion, codigos in ROLES_INICIALES:
        rol = Rol.objects.create(institucion=institucion, Code=code, nombre=nombre, descripcion=descripcion)
        rol.permisos.set(Permiso.objects.filter(codigo__in=codigos, vigente=True))
    from apps.cobranzas.servicios import crear_formas_iniciales
    crear_formas_iniciales(institucion)
    from apps.caja.servicios import crear_datos_iniciales
    crear_datos_iniciales(institucion)
    registrar('institucion_creada', request=request, usuario=actor, institucion=institucion,
              entidad='institucion', entidad_id=institucion.codigo, despues=foto_institucion(institucion),
              administrador_inicial=administrador.identificador)
    return institucion


@transaction.atomic
def cambiar_estado(institucion: Institucion, nuevo: str, *, motivo: str, actor=None, request=None) -> Institucion:
    """
    Suspende, archiva o reactiva una institución. El motivo es obligatorio y queda en la auditoría.
    Al suspender o archivar se cierran todas las sesiones abiertas de esa institución.
    """
    from apps.identidad.tokens import revocar_institucion

    institucion = Institucion.objects.select_for_update().get(pk=institucion.pk)
    motivo = (motivo or '').strip()
    if not motivo:
        raise ErrorNegocio('Indique el motivo del cambio de estado.')
    if nuevo not in TRANSICIONES.get(institucion.estado, set()):
        raise ErrorNegocio(f'No se puede pasar de «{institucion.get_estado_display()}» a «{Institucion.Estado(nuevo).label}».')
    anterior = institucion.estado
    institucion.estado = nuevo
    institucion.motivo_estado = motivo
    institucion.save(update_fields=['estado', 'motivo_estado', 'actualizado_en'])
    sesiones = revocar_institucion(institucion) if nuevo != Institucion.Estado.ACTIVA else 0
    registrar('institucion_estado', request=request, usuario=actor, institucion=institucion, entidad='institucion',
              entidad_id=institucion.codigo, motivo=motivo, antes={'estado': anterior}, despues={'estado': nuevo},
              sesiones_cerradas=sesiones)
    return institucion
