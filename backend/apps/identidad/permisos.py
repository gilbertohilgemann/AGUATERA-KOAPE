"""
Verificación de permisos en el servidor (nunca solo ocultando botones en la web).

Orden de verificación de cada endpoint (sección 5.3): sesión → institución (autenticación) →
permiso (esta clase) → estado del registro y flujo (servicios) → asignación al recorrido (Fase 3).
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Permiso


def permisos_efectivos(usuario) -> set[str]:
    """Códigos de permiso vigentes del usuario (todos si es administrador institucional)."""
    if usuario is None or not usuario.is_authenticated or usuario.institucion_id is None:
        return set()
    vigentes = Permiso.objects.filter(vigente=True)
    if getattr(usuario, 'es_integracion', False):
        # Credencial de integración: solo los permisos de consulta que le dio el administrador.
        return set(vigentes.filter(codigo__in=usuario.permisos).values_list('codigo', flat=True))
    if usuario.es_admin_institucion:
        return set(vigentes.values_list('codigo', flat=True))
    return set(
        vigentes.filter(
            roles__activo=True, roles__usuarios=usuario, roles__institucion_id=usuario.institucion_id,
        ).values_list('codigo', flat=True)
    )


def tiene_permiso(request, codigo: str) -> bool:
    return codigo in permisos_efectivos(request.user)


class RequierePermiso(BasePermission):
    """
    La vista declara `permiso_requerido = 'modulo.accion'`.

    Opcional: `permisos_lectura = (...)` permite CONSULTAR (GET) con cualquiera de esos permisos;
    por ejemplo, quien administra usuarios necesita ver la lista de roles para asignarlos.
    """

    message = 'No tiene permiso para realizar esta acción.'

    def has_permission(self, request, view):
        usuario = request.user
        if usuario is not None and getattr(usuario, 'debe_cambiar_contrasena', False):
            # Contraseña inicial o restablecida: hasta cambiarla solo puede usar auth/yo, auth/salir y
            # auth/cambiar-contrasena (que no usan esta clase).
            self.message = 'Debe cambiar su contraseña antes de continuar.'
            return False
        codigo = getattr(view, 'permiso_requerido', None)
        if not codigo:
            return False  # cerrado por defecto: una vista sin permiso declarado no se abre
        efectivos = permisos_efectivos(request.user)
        if codigo in efectivos:
            return True
        # `acciones_de_lectura`: acciones POST que no guardan nada (ej. simular una tarifa).
        if request.method in SAFE_METHODS or getattr(view, 'action', None) in getattr(view, 'acciones_de_lectura', ()):
            return any(otro in efectivos for otro in getattr(view, 'permisos_lectura', ()))
        return False
