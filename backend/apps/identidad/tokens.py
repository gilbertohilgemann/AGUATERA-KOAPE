"""Creación y revocación de tokens de sesión (se guarda solo el hash)."""
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import TokenSesion


def hash_de(clave: str) -> str:
    return hashlib.sha256(clave.encode('utf-8')).hexdigest()


def crear_token(usuario, request=None) -> tuple[TokenSesion, str]:
    clave = secrets.token_urlsafe(32)
    token = TokenSesion.objects.create(
        clave_hash=hash_de(clave),
        usuario=usuario,
        institucion=usuario.institucion,
        expira_en=timezone.now() + timedelta(hours=settings.KOAPE['VIGENCIA_TOKEN_HORAS']),
        ip=request.META.get('REMOTE_ADDR') if request is not None else None,
        agente=(request.META.get('HTTP_USER_AGENT', '') if request is not None else '')[:255],
    )
    return token, clave


def revocar(token: TokenSesion) -> None:
    if token.revocado_en is None:
        token.revocado_en = timezone.now()
        token.save(update_fields=['revocado_en'])


def revocar_todos(usuario, excepto: TokenSesion | None = None) -> int:
    consulta = TokenSesion.objects.filter(usuario=usuario, revocado_en__isnull=True)
    if excepto is not None:
        consulta = consulta.exclude(pk=excepto.pk)
    return consulta.update(revocado_en=timezone.now())


def revocar_institucion(institucion) -> int:
    """Cierra todas las sesiones de una institución (al suspenderla o archivarla)."""
    return TokenSesion.objects.filter(institucion=institucion, revocado_en__isnull=True).update(
        revocado_en=timezone.now())
