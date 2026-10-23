"""
Backup completo (módulo de la convención).

Un .zip con: todo el código (backend + frontend + scripts), media/ y los archivos privados (fotos,
comprobantes), la base SQLite tal cual esté (copia consistente aunque el sistema esté escribiendo)
y un `pg_dump` si el sistema corre sobre PostgreSQL. Incluye `backend/.env`.

Exclusiones fijas:
- Lo que se regenera solo: venv/, node_modules/, __pycache__/, dist/, .vite/, staticfiles/.
- Por seguridad, todo rastro del repositorio: .git/ completa, .github/, .gitignore, .gitattributes,
  .gitmodules. Un backup nunca debe delatar dónde vive el código.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.db import connections
from django.utils import timezone

DIRECTORIOS_EXCLUIDOS = {
    'venv', '.venv', 'env', 'node_modules', '__pycache__', 'dist', '.vite', 'staticfiles',
    '.git', '.github', '.run', 'logs', '.pytest_cache', '.mypy_cache', 'herramientas',
}
ARCHIVOS_EXCLUIDOS = {'.gitignore', '.gitattributes', '.gitmodules'}
EXTENSIONES_EXCLUIDAS = {'.pyc', '.pyo'}


def _marca_tiempo() -> str:
    return timezone.localtime().strftime('%Y%m%d-%H%M%S')


def _nombre_libre(directorio: Path, base: str) -> Path:
    """Nunca pisa un respaldo existente (dos respaldos en el mismo segundo)."""
    destino = directorio / f'{base}.zip'
    n = 2
    while destino.exists():
        destino = directorio / f'{base}-{n}.zip'
        n += 1
    return destino


def copiar_sqlite(origen: Path, destino: Path) -> None:
    """Copia consistente aunque el sistema esté escribiendo (API de backup de SQLite)."""
    fuente = sqlite3.connect(str(origen))
    try:
        copia = sqlite3.connect(str(destino))
        try:
            fuente.backup(copia)
        finally:
            copia.close()
    finally:
        fuente.close()


def volcar_postgres(cfg: dict, destino: Path) -> str | None:
    """Ejecuta pg_dump. Devuelve un mensaje de advertencia si no se pudo."""
    ejecutable = shutil.which('pg_dump')
    if not ejecutable:
        return f'pg_dump no está instalado: no se incluyó el volcado de {cfg["NAME"]}.'
    entorno = dict(os.environ, PGPASSWORD=cfg.get('PASSWORD') or '')
    comando = [ejecutable, '--no-owner', '--no-privileges', '-h', cfg.get('HOST') or 'localhost',
               '-p', str(cfg.get('PORT') or 5432), '-U', cfg.get('USER') or '', '-f', str(destino), cfg['NAME']]
    resultado = subprocess.run(comando, env=entorno, capture_output=True, text=True)
    if resultado.returncode != 0:
        return f'pg_dump falló para {cfg["NAME"]}: {resultado.stderr.strip()[:300]}'
    return None


def _recorrer_codigo(raiz: Path, excluir: set[Path]):
    for actual, directorios, archivos in os.walk(raiz):
        actual_p = Path(actual)
        directorios[:] = [
            d for d in directorios
            if d not in DIRECTORIOS_EXCLUIDOS and (actual_p / d).resolve() not in excluir
        ]
        for archivo in archivos:
            ruta = actual_p / archivo
            if archivo in ARCHIVOS_EXCLUIDOS or ruta.suffix in EXTENSIONES_EXCLUIDAS:
                continue
            yield ruta


def generar_respaldo() -> Path:
    destino_dir = Path(settings.DIR_RESPALDOS)
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = _nombre_libre(destino_dir, f'koape-aguateras-respaldo-{_marca_tiempo()}')
    raiz = Path(settings.RAIZ_PROYECTO)
    # Los datos se agregan aparte (copia consistente); los respaldos anteriores no se meten dentro del nuevo.
    excluir = {Path(settings.DIR_DATOS).resolve(), Path(settings.DIR_RESPALDOS).resolve()}
    advertencias: list[str] = []
    cfg = connections['default'].settings_dict
    motor = connections['default'].vendor

    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(destino, 'w', zipfile.ZIP_DEFLATED) as zipf:
        temporal = Path(tmp)
        for ruta in _recorrer_codigo(raiz, excluir):
            zipf.write(ruta, Path('codigo') / ruta.relative_to(raiz))
        # Archivos privados fuera de la carpeta del proyecto (si se configuró DIR_PRIVADO en otro disco).
        privado = Path(settings.DIR_PRIVADO)
        if privado.exists() and raiz.resolve() not in privado.resolve().parents:
            for ruta in privado.rglob('*'):
                if ruta.is_file():
                    zipf.write(ruta, Path('privado') / ruta.relative_to(privado))

        if motor == 'sqlite':
            copia = temporal / 'aguateras.sqlite3'
            copiar_sqlite(Path(cfg['NAME']), copia)
            zipf.write(copia, 'base/aguateras.sqlite3')
        else:
            volcado = temporal / 'aguateras.sql'
            aviso = volcar_postgres(cfg, volcado)
            if aviso:
                advertencias.append(aviso)
            else:
                zipf.write(volcado, 'base/aguateras.sql')
        # Copias SQLite que hayan quedado de «traer datos de PostgreSQL a SQLite» (módulo de migración).
        if motor != 'sqlite':
            for copia in sorted(Path(settings.DIR_DATOS).glob('*.sqlite3')):
                temporal_copia = temporal / f'disco-{copia.name}'
                copiar_sqlite(copia, temporal_copia)
                zipf.write(temporal_copia, f'base/sqlite-en-disco/{copia.name}')

        zipf.writestr('manifiesto.json', json.dumps({
            'tipo': 'koape-aguateras',
            'generado_en': timezone.localtime().isoformat(),
            'motor': motor,
            'advertencias': advertencias,
        }, ensure_ascii=False, indent=2))
    return destino


def limpiar_viejos(directorio: Path, conservar: int) -> None:
    archivos = sorted(directorio.glob('*.zip'), key=lambda p: p.stat().st_mtime, reverse=True)
    for viejo in archivos[conservar:]:
        viejo.unlink(missing_ok=True)


def respaldos_guardados() -> list[Path]:
    carpeta = Path(settings.DIR_RESPALDOS)
    if not carpeta.exists():
        return []
    return sorted(carpeta.glob('*.zip'), key=lambda p: p.stat().st_mtime, reverse=True)
