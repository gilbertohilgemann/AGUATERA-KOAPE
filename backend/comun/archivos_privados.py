"""
Archivos privados: fotos de viviendas y medidores, comprobantes.

- Se guardan en DIR_PRIVADO (fuera de media/), nunca en una ruta pública predecible.
- Solo los entregan endpoints que verifican sesión, institución y permiso (`respuesta_archivo`).
- Se valida el contenido real (firma del archivo), no solo la extensión, y el tamaño máximo.
- Nombre aleatorio: el nombre original del usuario nunca llega al disco.
- No se borran al reemplazarlos (sección 6: nada desaparece en silencio); la referencia vieja queda en
  la auditoría.
"""
import uuid
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from django.utils import timezone

from .errores import ErrorNegocio

TAMANO_MAXIMO = 8 * 1024 * 1024  # 8 MB (las fotos se comprimen en el teléfono antes de subir)

FIRMAS = {
    'jpg': (b'\xff\xd8\xff',),
    'png': (b'\x89PNG\r\n\x1a\n',),
    'webp': (b'RIFF',),  # + 'WEBP' en el byte 8
    'pdf': (b'%PDF-',),
}
TIPOS_MIME = {'jpg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp', 'pdf': 'application/pdf'}
IMAGENES = ('jpg', 'png', 'webp')


def detectar_tipo(cabecera: bytes) -> str | None:
    for tipo, firmas in FIRMAS.items():
        if any(cabecera.startswith(f) for f in firmas):
            if tipo == 'webp' and cabecera[8:12] != b'WEBP':
                continue
            return tipo
    return None


def guardar(institucion, categoria: str, archivo, permitidos=IMAGENES) -> str:
    """Valida y guarda el archivo subido. Devuelve la ruta relativa (lo que se guarda en la base)."""
    if archivo is None:
        raise ErrorNegocio('No se recibió ningún archivo.')
    if archivo.size > TAMANO_MAXIMO:
        raise ErrorNegocio(f'El archivo supera el máximo de {TAMANO_MAXIMO // (1024 * 1024)} MB.')
    archivo.seek(0)
    tipo = detectar_tipo(archivo.read(16))
    archivo.seek(0)
    if tipo not in permitidos:
        raise ErrorNegocio('Tipo de archivo no permitido. Use una foto JPG, PNG o WEBP.'
                           if permitidos == IMAGENES else 'Tipo de archivo no permitido.')
    relativo = Path(str(institucion.pk)) / categoria / timezone.localdate().strftime('%Y/%m') / f'{uuid.uuid4().hex}.{tipo}'
    destino = Path(settings.DIR_PRIVADO) / relativo
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, 'wb') as salida:
        for trozo in archivo.chunks():
            salida.write(trozo)
    return relativo.as_posix()


def ruta_absoluta(institucion, relativo: str) -> Path:
    """Resuelve la ruta y verifica que esté dentro de la carpeta de ESA institución."""
    base = (Path(settings.DIR_PRIVADO) / str(institucion.pk)).resolve()
    ruta = (Path(settings.DIR_PRIVADO) / relativo).resolve()
    if base not in ruta.parents or not ruta.is_file():
        raise Http404('Archivo no encontrado.')
    return ruta


def respuesta_archivo(institucion, relativo: str) -> FileResponse:
    if not relativo:
        raise Http404('No hay archivo.')
    ruta = ruta_absoluta(institucion, relativo)
    tipo = ruta.suffix.lstrip('.')
    respuesta = FileResponse(open(ruta, 'rb'), content_type=TIPOS_MIME.get(tipo, 'application/octet-stream'))
    respuesta['Cache-Control'] = 'private, max-age=300'
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta
