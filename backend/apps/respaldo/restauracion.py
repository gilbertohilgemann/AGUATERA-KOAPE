"""
Verificación y restauración de respaldos.

Reglas:
- Antes de restaurar se VERIFICA el ZIP completo (CRC, manifiesto, integridad de la base SQLite y que
  no sea de una versión más nueva del sistema). Si algo falla, no se toca nada.
- Antes de pisar datos se genera un respaldo PREVIO de lo que hay ahora (se puede deshacer).
- Se restaura con el sistema detenido (`start restaurar <archivo>` lo detiene y lo vuelve a arrancar).
- Después se aplican las migraciones pendientes (el respaldo puede ser de una versión anterior).
- El código no se toca: se restauran la base, media/ y los archivos privados.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.db import connections
from django.db.migrations.loader import MigrationLoader

from .servicios import copiar_sqlite, generar_respaldo


class ErrorRestauracion(Exception):
    pass


def _migraciones_conocidas() -> set[tuple[str, str]]:
    return set(MigrationLoader(None, ignore_no_migrations=True).disk_migrations)


def _revisar_sqlite(ruta: Path, conocidas: set) -> dict:
    conexion = sqlite3.connect(str(ruta))
    try:
        integridad = conexion.execute('PRAGMA integrity_check').fetchone()[0]
        tablas = [f[0] for f in conexion.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        aplicadas = set()
        if 'django_migrations' in tablas:
            aplicadas = {(a, n) for a, n in conexion.execute('SELECT app, name FROM django_migrations')}
    finally:
        conexion.close()
    desconocidas = sorted(f'{a}.{n}' for a, n in aplicadas - conocidas)
    return {'motor': 'sqlite', 'integridad': integridad, 'tablas': len(tablas), 'migraciones': len(aplicadas),
            'migraciones_desconocidas': desconocidas}


def _nombre_seguro(nombre: str) -> bool:
    ruta = PurePosixPath(nombre)
    return not ruta.is_absolute() and '..' not in ruta.parts and '\\' not in nombre and ':' not in nombre


def verificar(ruta_zip) -> dict:
    """Revisa un respaldo sin restaurarlo. `errores` vacío = se puede restaurar."""
    ruta_zip = Path(ruta_zip)
    informe = {'archivo': str(ruta_zip), 'manifiesto': {}, 'base': None, 'archivos': 0, 'errores': [], 'avisos': []}
    if not ruta_zip.is_file():
        informe['errores'].append('No existe el archivo.')
        return informe
    try:
        zipf = zipfile.ZipFile(ruta_zip)
    except zipfile.BadZipFile:
        informe['errores'].append('No es un ZIP válido (archivo dañado o incompleto).')
        return informe
    with zipf, tempfile.TemporaryDirectory() as tmp:
        dañado = zipf.testzip()
        if dañado:
            informe['errores'].append(f'El ZIP está dañado: falla la verificación de {dañado}.')
            return informe
        nombres = zipf.namelist()
        inseguros = [n for n in nombres if not _nombre_seguro(n)]
        if inseguros:
            informe['errores'].append(f'El ZIP contiene rutas no permitidas: {inseguros[:3]}')
            return informe
        if 'manifiesto.json' not in nombres:
            informe['errores'].append('Falta manifiesto.json: no es un respaldo de Koape Aguateras.')
            return informe
        try:
            manifiesto = json.loads(zipf.read('manifiesto.json'))
        except ValueError:
            manifiesto = None
        if not isinstance(manifiesto, dict):
            informe['errores'].append('manifiesto.json está dañado.')
            return informe
        informe['manifiesto'] = manifiesto
        informe['avisos'].extend(manifiesto.get('advertencias') or [])
        if manifiesto.get('tipo') != 'koape-aguateras':
            informe['errores'].append(f'Tipo de respaldo desconocido: {manifiesto.get("tipo")!r}.')
            return informe
        informe['archivos'] = sum(1 for n in nombres if n.startswith('codigo/'))
        if 'base/aguateras.sqlite3' in nombres:
            destino = Path(tmp) / 'revisar.sqlite3'
            destino.write_bytes(zipf.read('base/aguateras.sqlite3'))
            try:
                datos = _revisar_sqlite(destino, _migraciones_conocidas())
            except sqlite3.DatabaseError as error:
                informe['errores'].append(f'La base no es una base SQLite legible ({error}).')
                return informe
            informe['base'] = datos
            if datos['integridad'] != 'ok':
                informe['errores'].append(f'La base está dañada ({datos["integridad"][:120]}).')
            if datos['migraciones_desconocidas']:
                informe['errores'].append(
                    f'La base es de una versión MÁS NUEVA del sistema ({", ".join(datos["migraciones_desconocidas"][:3])}…). '
                    'Actualice el sistema antes de restaurar.')
        elif 'base/aguateras.sql' in nombres:
            informe['base'] = {'motor': 'postgresql', 'tamano': zipf.getinfo('base/aguateras.sql').file_size}
        else:
            informe['errores'].append('El respaldo no trae la base de datos.')
    return informe


def _restaurar_postgres(cfg: dict, archivo_sql: Path) -> None:
    psql = shutil.which('psql')
    if not psql:
        raise ErrorRestauracion('psql no está instalado: no se puede restaurar una base PostgreSQL desde esta computadora.')
    entorno = dict(os.environ, PGPASSWORD=cfg.get('PASSWORD') or '')
    base = [psql, '-v', 'ON_ERROR_STOP=1', '-h', cfg.get('HOST') or 'localhost', '-p', str(cfg.get('PORT') or 5432),
            '-U', cfg.get('USER') or '', '-d', cfg['NAME']]
    # Borrado y carga en UNA transacción: si la carga falla, la base queda como estaba.
    comando = base + ['--single-transaction', '-c', 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;',
                      '-f', str(archivo_sql)]
    resultado = subprocess.run(comando, env=entorno, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise ErrorRestauracion(f'psql falló en {cfg["NAME"]} (no se cambió nada): {resultado.stderr.strip()[:300]}')


def _reponer_archivos(zipf: zipfile.ZipFile, prefijo: str, destino: Path) -> int:
    """Reemplaza la carpeta `destino` por lo que hay bajo `prefijo` en el ZIP."""
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True, exist_ok=True)
    cantidad = 0
    for info in zipf.infolist():
        if not info.filename.startswith(prefijo) or info.is_dir():
            continue
        relativo = PurePosixPath(info.filename[len(prefijo):])
        salida = destino.joinpath(*relativo.parts)
        if destino.resolve() not in salida.resolve().parents:
            continue
        salida.parent.mkdir(parents=True, exist_ok=True)
        with zipf.open(info) as origen, open(salida, 'wb') as archivo:
            shutil.copyfileobj(origen, archivo)
        cantidad += 1
    return cantidad


def _prefijo_en_codigo(carpeta: Path) -> str | None:
    raiz = Path(settings.RAIZ_PROYECTO).resolve()
    try:
        return 'codigo/' + carpeta.resolve().relative_to(raiz).as_posix() + '/'
    except ValueError:
        return None


def restaurar(ruta_zip, *, respaldo_previo=True) -> dict:
    """Restaura la base, media/ y los archivos privados. El código no se toca."""
    with tempfile.TemporaryDirectory() as tmp_copia:
        # Se trabaja sobre una copia: generar el respaldo previo limpia los viejos y podría borrar el original.
        copia = Path(tmp_copia) / Path(ruta_zip).name
        shutil.copy2(ruta_zip, copia)
        informe = verificar(copia)
        if informe['errores']:
            raise ErrorRestauracion('El respaldo no pasó la verificación: ' + ' '.join(informe['errores']))
        previo = generar_respaldo() if respaldo_previo else None
        if previo is not None:
            control = verificar(previo)
            if control['errores'] or control['avisos'] or not control['base']:
                raise ErrorRestauracion(
                    'No se pudo respaldar lo actual antes de restaurar (¿falta pg_dump?): no se tocó nada. '
                    + ' '.join(control['errores'] + control['avisos']))
        cfg = connections['default'].settings_dict
        es_sqlite = connections['default'].vendor == 'sqlite'
        with zipfile.ZipFile(copia) as zipf, tempfile.TemporaryDirectory() as tmp:
            nombres = set(zipf.namelist())
            nombre = 'base/aguateras.sqlite3' if es_sqlite else 'base/aguateras.sql'
            if nombre not in nombres:
                raise ErrorRestauracion(
                    'El respaldo es de otro motor de base de datos: pase primero el sistema al mismo motor '
                    '(panel «Migración de base de datos»).')
            extraido = Path(tmp) / Path(nombre).name
            extraido.write_bytes(zipf.read(nombre))
            connections['default'].close()
            if es_sqlite:
                copiar_sqlite(extraido, Path(cfg['NAME']))
            else:
                _restaurar_postgres(cfg, extraido)
            connections['default'].close()
            archivos = 0
            for carpeta in (Path(settings.MEDIA_ROOT), Path(settings.DIR_PRIVADO)):
                prefijo = _prefijo_en_codigo(carpeta)
                if prefijo and any(n.startswith(prefijo) for n in nombres):
                    archivos += _reponer_archivos(zipf, prefijo, carpeta)
            if any(n.startswith('privado/') for n in nombres):
                archivos += _reponer_archivos(zipf, 'privado/', Path(settings.DIR_PRIVADO))
    from django.core.management import call_command
    call_command('migrate', interactive=False, verbosity=0)
    from apps.auditoria.servicios import registrar
    registrar('respaldo_restaurado', usuario_nombre='consola', entidad='respaldo', entidad_id=Path(ruta_zip).name,
              generado_en=informe['manifiesto'].get('generado_en'), respaldo_previo=previo.name if previo else '')
    return {'archivos': archivos, 'respaldo_previo': str(previo or '')}
