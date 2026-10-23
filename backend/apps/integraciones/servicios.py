import secrets

from django.db import transaction
from django.utils import timezone

from apps.auditoria.servicios import registrar
from apps.identidad.tokens import hash_de
from comun.errores import ErrorNegocio

from .autenticacion import PERMISOS_ASIGNABLES
from .models import CredencialIntegracion

ALFABETO = 'abcdefghjkmnpqrstuvwxyz23456789'


def foto(c: CredencialIntegracion) -> dict:
    return {'prefijo': c.prefijo, 'nombre': c.nombre, 'permisos': c.permisos, 'limite_por_minuto': c.limite_por_minuto,
            'expira_en': c.expira_en.isoformat() if c.expira_en else None, 'activa': c.activa}


def crear(*, institucion, nombre: str, permisos: list, limite_por_minuto: int = 60, expira_en=None, usuario,
          request=None) -> tuple[CredencialIntegracion, str]:
    """Devuelve la credencial y la CLAVE completa, que se muestra una sola vez (solo se guarda su hash)."""
    nombre = (nombre or '').strip()
    if not nombre:
        raise ErrorNegocio('Indique para qué sistema es la credencial.')
    permisos = sorted(set(permisos or []))
    invalidos = [p for p in permisos if p not in PERMISOS_ASIGNABLES]
    if invalidos or not permisos:
        raise ErrorNegocio('Elija al menos un permiso de consulta válido.' if not invalidos
                           else f'Permisos no asignables a una integración: {", ".join(invalidos)}.')
    from apps.identidad.permisos import permisos_efectivos
    ajenos = [p for p in permisos if p not in permisos_efectivos(usuario)]
    if ajenos:
        # Nadie da a otro sistema más acceso del que tiene él mismo.
        raise ErrorNegocio(f'No puede dar permisos que usted no tiene: {", ".join(ajenos)}.', codigo='permiso_ajeno')
    if not 1 <= int(limite_por_minuto) <= 600:
        raise ErrorNegocio('El límite debe estar entre 1 y 600 solicitudes por minuto.')
    if expira_en is not None and expira_en <= timezone.now():
        raise ErrorNegocio('La fecha de vencimiento ya pasó.')
    with transaction.atomic():
        for _ in range(20):
            prefijo = ''.join(secrets.choice(ALFABETO) for _ in range(8))
            if not CredencialIntegracion.objects.filter(prefijo=prefijo).exists():
                break
        clave = f'kpa_{prefijo}_{secrets.token_urlsafe(32)}'
        credencial = CredencialIntegracion.objects.create(
            institucion=institucion, nombre=nombre[:120], prefijo=prefijo, clave_hash=hash_de(clave), permisos=permisos,
            limite_por_minuto=int(limite_por_minuto), expira_en=expira_en, creada_por=usuario)
        registrar('credencial_integracion_creada', request=request, usuario=usuario, institucion=institucion,
                  entidad='credencial_integracion', entidad_id=prefijo, despues=foto(credencial))
    return credencial, clave


def revocar(credencial: CredencialIntegracion, *, motivo: str, usuario, request=None) -> CredencialIntegracion:
    motivo = (motivo or '').strip()
    if not motivo:
        raise ErrorNegocio('Indique el motivo de la revocación.')
    with transaction.atomic():
        credencial = CredencialIntegracion.objects.select_for_update().get(pk=credencial.pk)
        if not credencial.activa:
            raise ErrorNegocio('La credencial ya está revocada.')
        antes = foto(credencial)
        credencial.activa = False
        credencial.revocada_por, credencial.revocada_en, credencial.motivo_revocacion = usuario, timezone.now(), motivo
        credencial.save()
        registrar('credencial_integracion_revocada', request=request, usuario=usuario,
                  institucion=credencial.institucion, entidad='credencial_integracion', entidad_id=credencial.prefijo,
                  motivo=motivo, antes=antes, despues=foto(credencial))
    return credencial
