"""
Cifrado de secretos guardados en la base (credenciales de integraciones, p. ej. el proveedor de factura electrónica).

Solo biblioteca estándar: flujo HMAC-SHA256 en modo contador + HMAC de integridad (cifrar y después
autenticar). La clave sale de CLAVE_CIFRADO en backend/.env (o, si no está, de SECRET_KEY): sin esa
clave los valores de la base no se pueden leer, y cualquier alteración se detecta.

Si se cambia la clave, los secretos guardados dejan de poder leerse y hay que volver a cargarlos.
"""
import base64
import hashlib
import hmac
import os

from django.conf import settings

VERSION = b'k1'


class SecretoIlegible(Exception):
    """El valor fue alterado o se cifró con otra clave."""


def _claves() -> tuple[bytes, bytes]:
    maestra = (getattr(settings, 'CLAVE_CIFRADO', '') or settings.SECRET_KEY).encode()
    return (hmac.new(maestra, b'koape-cifrado', hashlib.sha256).digest(),
            hmac.new(maestra, b'koape-integridad', hashlib.sha256).digest())


def _flujo(clave: bytes, nonce: bytes, largo: int) -> bytes:
    bloques, contador = [], 0
    while sum(len(b) for b in bloques) < largo:
        bloques.append(hmac.new(clave, nonce + contador.to_bytes(8, 'big'), hashlib.sha256).digest())
        contador += 1
    return b''.join(bloques)[:largo]


def cifrar(texto: str) -> str:
    if not texto:
        return ''
    clave, integridad = _claves()
    nonce = os.urandom(16)
    datos = texto.encode('utf-8')
    cifrado = bytes(a ^ b for a, b in zip(datos, _flujo(clave, nonce, len(datos))))
    marca = hmac.new(integridad, VERSION + nonce + cifrado, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(VERSION + nonce + marca + cifrado).decode()


def descifrar(valor: str) -> str:
    if not valor:
        return ''
    try:
        crudo = base64.urlsafe_b64decode(valor.encode())
    except (ValueError, TypeError) as error:
        raise SecretoIlegible('Valor cifrado dañado.') from error
    if crudo[:2] != VERSION or len(crudo) < 50:
        raise SecretoIlegible('Formato de secreto desconocido.')
    nonce, marca, cifrado = crudo[2:18], crudo[18:50], crudo[50:]
    clave, integridad = _claves()
    if not hmac.compare_digest(marca, hmac.new(integridad, VERSION + nonce + cifrado, hashlib.sha256).digest()):
        raise SecretoIlegible('El secreto fue alterado o se cifró con otra clave (¿cambió CLAVE_CIFRADO?).')
    return bytes(a ^ b for a, b in zip(cifrado, _flujo(clave, nonce, len(cifrado)))).decode('utf-8')


def pista(texto: str) -> str:
    """Para mostrar sin revelar: «••••1234»."""
    return f'••••{texto[-4:]}' if len(texto) > 6 else '••••'
