"""
Registro de auditoría.

`registrar()` se llama desde los servicios de cada módulo. Nunca se guardan contraseñas, tokens ni
secretos: las claves sensibles se descartan de `detalle`, `antes` y `despues`.
"""
from .models import RegistroAuditoria

CLAVES_PROHIBIDAS = {
    'contrasena', 'contrasena_actual', 'contrasena_nueva', 'password', 'token', 'clave', 'clave_hash',
    'secreto', 'secret', 'api_key', 'credenciales',
}


def _prohibida(clave) -> bool:
    texto = str(clave).lower()
    return any(p in texto for p in CLAVES_PROHIBIDAS) and texto != 'debe_cambiar_contrasena'


def _limpiar(datos):
    if isinstance(datos, dict):
        return {k: _limpiar(v) for k, v in datos.items() if not _prohibida(k)}
    if isinstance(datos, list):
        return [_limpiar(v) for v in datos]
    return datos


def ip_cliente(request) -> str | None:
    """IP real del cliente: con NUM_PROXIES, la que agregó el último proxy de confianza; si no, REMOTE_ADDR."""
    from django.conf import settings

    proxies = settings.REST_FRAMEWORK.get('NUM_PROXIES')
    remota = request.META.get('REMOTE_ADDR')
    reenviada = request.META.get('HTTP_X_FORWARDED_FOR')
    if proxies and reenviada:
        direcciones = [d.strip() for d in reenviada.split(',') if d.strip()]
        if direcciones:
            return direcciones[-min(proxies, len(direcciones))]
    return remota


def _solicitud_django(request):
    return getattr(request, '_request', request)


def registrar(accion: str, *, request=None, usuario=None, institucion=None, entidad: str = '', entidad_id='',
              resultado: str = RegistroAuditoria.Resultado.EXITO, motivo: str = '', antes=None, despues=None,
              **detalle) -> RegistroAuditoria:
    """
    Guarda un evento. Si no se indican, el usuario y la institución salen de la solicitud autenticada.
    """
    base = _solicitud_django(request) if request is not None else None
    if usuario is None and request is not None:
        posible = getattr(request, 'user', None)
        if posible is not None and getattr(posible, 'is_authenticated', False):
            usuario = posible
    if institucion is None:
        institucion = getattr(base, 'institucion', None) if base is not None else None
        if institucion is None and usuario is not None:
            institucion = getattr(usuario, 'institucion', None) if not hasattr(usuario, 'documento') else None
    nombre = detalle.pop('usuario_nombre', None) or (getattr(usuario, 'identificador', '') if usuario else '')
    from django.contrib.auth import get_user_model
    # Solo un usuario del sistema va en la relación; otros (credencial de integración, cuenta del portal de abonados)
    # quedan identificados por su nombre.
    es_usuario = isinstance(usuario, get_user_model()) and usuario.pk is not None
    if usuario is not None and not es_usuario and not nombre:
        nombre = str(usuario)
    return RegistroAuditoria.objects.create(
        institucion=institucion,
        usuario=usuario if es_usuario else None,
        usuario_nombre=(nombre or '')[:180],
        accion=accion,
        entidad=entidad,
        entidad_id=str(entidad_id or ''),
        resultado=resultado,
        motivo=motivo,
        antes=_limpiar(antes) if antes is not None else None,
        despues=_limpiar(despues) if despues is not None else None,
        detalle=_limpiar(detalle),
        ip=ip_cliente(base) if base is not None else None,
        id_solicitud=getattr(base, 'id_solicitud', '') if base is not None else '',
    )
