"""Ayudas para las pruebas: instituciones, usuarios y clientes de API autenticados."""
from rest_framework.test import APIClient

from apps.identidad.models import Permiso, Rol, Usuario
from apps.plataforma.models import Institucion
from apps.plataforma.servicios import crear_institucion

CONTRASENA = 'Clave.Segura.2026'


def nueva_institucion(codigo: str, nombre: str | None = None) -> Institucion:
    return crear_institucion(datos={'codigo': codigo, 'nombre': nombre or f'Institución {codigo}'},
                             admin_usuario='admin', admin_contrasena=CONTRASENA)


def admin_de(institucion) -> Usuario:
    usuario = Usuario.objects.get(institucion=institucion, nombre_usuario='admin')
    if usuario.debe_cambiar_contrasena:
        usuario.debe_cambiar_contrasena = False
        usuario.save(update_fields=['debe_cambiar_contrasena'])
    return usuario


def usuario_con_permisos(institucion, nombre: str, codigos: list[str]) -> Usuario:
    usuario = Usuario(institucion=institucion, nombre_usuario=nombre)
    usuario.set_password(CONTRASENA)
    usuario.save()
    if codigos:
        rol = Rol.objects.create(institucion=institucion, Code=f'ROL-{nombre}'.upper(), nombre=f'Rol de {nombre}')
        rol.permisos.set(Permiso.objects.filter(codigo__in=codigos))
        usuario.roles.add(rol)
    return usuario


def cliente_de(institucion, usuario: str = 'admin', contrasena: str = CONTRASENA) -> APIClient:
    """Ingresa por la API (el mismo camino que la web) y devuelve el cliente con el token puesto."""
    cliente = APIClient()
    respuesta = cliente.post('/api/v1/auth/ingresar/', {
        'codigo_institucion': institucion.codigo, 'usuario': usuario, 'contrasena': contrasena,
    }, format='json')
    assert respuesta.status_code == 200, respuesta.content
    cliente.credentials(HTTP_AUTHORIZATION=f'Token {respuesta.data["token"]}')
    return cliente


class LimpiarLimites:
    """Mixin: limpia el contador de intentos de ingreso (throttling) entre pruebas."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        super().setUp()
