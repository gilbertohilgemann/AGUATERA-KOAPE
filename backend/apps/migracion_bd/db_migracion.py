"""
Migración SQLite ⇄ PostgreSQL sin perder datos (módulo de la convención).

Cómo:
- La base destino se registra como alias de conexión TEMPORAL (`connections.databases[alias] = {...}`):
  no se toca settings.DATABASES ni hace falta reiniciar para copiar.
- Se crean las tablas con `migrate` y se copian los datos con dumpdata/loaddata (Django resuelve solo
  el orden de las claves foráneas y las relaciones muchos a muchos).
- Al final se actualiza `backend/.env`; el sistema pasa al motor nuevo al reiniciar (start restart).

Acciones:
1. migrar_a_postgres     → la base pasa a PostgreSQL.
2. volver_a_sqlite        → la base vuelve a un archivo SQLite.
3. traer_datos_a_sqlite   → copia los datos de PostgreSQL a SQLite SIN cambiar de motor (útil antes de un
                            backup para llevar los datos reales a otra PC sin restaurar un volcado SQL a mano).

Nota PostGIS: el motor de producción será PostGIS cuando lleguen los mapas (Fase 2). PostGIS es
PostgreSQL con una extensión: esta copia sirve igual.
"""
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.db import connections

EXCLUIR_DEL_VOLCADO = ['contenttypes', 'auth.permission', 'sessions']
ALIAS_DESTINO = 'destino_migracion'


@dataclass
class DatosPostgres:
    servidor: str
    puerto: str
    usuario: str
    contrasena: str
    nombre: str = 'koape_aguateras'


class ErrorMigracion(Exception):
    pass


def _nombre_seguro(texto: str) -> str:
    return re.sub(r'[^a-z0-9_]', '_', (texto or '').lower())


def configuracion_postgres(datos: DatosPostgres) -> dict:
    return {
        'ENGINE': 'django.db.backends.postgresql', 'NAME': _nombre_seguro(datos.nombre), 'USER': datos.usuario,
        'PASSWORD': datos.contrasena, 'HOST': datos.servidor, 'PORT': str(datos.puerto),
    }


def configuracion_sqlite(ruta: Path) -> dict:
    return {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(ruta), 'OPTIONS': dict(settings.OPCIONES_SQLITE)}


def registrar_alias(alias: str, cfg: dict) -> None:
    quitar_alias(alias)
    base = connections['default'].settings_dict
    completa = {**{k: v for k, v in base.items() if k not in {'ENGINE', 'NAME', 'USER', 'PASSWORD', 'HOST', 'PORT',
                                                               'OPTIONS'}}, 'OPTIONS': {}, **cfg}
    completa.setdefault('TEST', {})
    connections.databases[alias] = completa


def quitar_alias(alias: str) -> None:
    if alias in connections.databases:
        try:
            connections[alias].close()
        except Exception:
            pass
        del connections.databases[alias]
        if hasattr(connections._connections, alias):
            delattr(connections._connections, alias)


def probar_conexion(datos: DatosPostgres) -> None:
    import psycopg

    try:
        with psycopg.connect(host=datos.servidor, port=datos.puerto, user=datos.usuario,
                             password=datos.contrasena, dbname='postgres', connect_timeout=5):
            pass
    except Exception as error:
        raise ErrorMigracion(f'No se pudo conectar a PostgreSQL: {error}')


def crear_base_si_no_existe(datos: DatosPostgres) -> None:
    import psycopg
    from psycopg import sql

    with psycopg.connect(host=datos.servidor, port=datos.puerto, user=datos.usuario, password=datos.contrasena,
                         dbname='postgres', autocommit=True) as conexion:
        nombre = _nombre_seguro(datos.nombre)
        if not conexion.execute('SELECT 1 FROM pg_database WHERE datname = %s', [nombre]).fetchone():
            # Siempre UTF-8 (desde template0): en un servidor creado como SQL_ASCII los acentos y la auditoría (JSON)
            # fallarían con «unsupported Unicode escape sequence».
            conexion.execute(sql.SQL("CREATE DATABASE {} ENCODING 'UTF8' TEMPLATE template0").format(
                sql.Identifier(nombre)))
        codificacion = conexion.execute('SELECT pg_encoding_to_char(encoding) FROM pg_database WHERE datname = %s',
                                        [nombre]).fetchone()[0]
        if codificacion != 'UTF8':
            raise ErrorMigracion(f'La base «{nombre}» ya existe con codificación {codificacion}: debe ser UTF8. '
                                 'Créela de nuevo con ENCODING \'UTF8\' o use otro nombre.')


def _excluidos() -> list[str]:
    """
    Lo que no se copia: tablas que Django regenera solo y los modelos «sin tabla» de los paneles del admin
    (dumpdata no los saltea por sí mismo e intentaría leer una tabla que no existe).
    """
    from django.apps import apps

    sin_tabla = [f'{m._meta.app_label}.{m.__name__}' for m in apps.get_models() if not m._meta.managed]
    return EXCLUIR_DEL_VOLCADO + sin_tabla


def copiar_datos(alias_origen: str, alias_destino: str) -> None:
    """Crea las tablas en el destino, lo vacía y copia todos los datos del origen."""
    call_command('migrate', database=alias_destino, interactive=False, verbosity=0)
    call_command('flush', database=alias_destino, interactive=False, verbosity=0)
    with tempfile.TemporaryDirectory() as tmp:
        archivo = Path(tmp) / 'datos.json'
        call_command('dumpdata', database=alias_origen, natural_foreign=True, exclude=_excluidos(),
                     output=str(archivo), verbosity=0)
        call_command('loaddata', str(archivo), database=alias_destino, verbosity=0)


def actualizar_env(valores: dict) -> None:
    """Reescribe claves de backend/.env conservando el resto del archivo."""
    ruta = Path(settings.BASE_DIR) / '.env'
    lineas = ruta.read_text(encoding='utf-8').splitlines() if ruta.exists() else []
    pendientes = dict(valores)
    nuevas = []
    for linea in lineas:
        clave = linea.split('=', 1)[0].strip() if '=' in linea and not linea.lstrip().startswith('#') else None
        if clave in pendientes:
            nuevas.append(f'{clave}={pendientes.pop(clave)}')
        else:
            nuevas.append(linea)
    nuevas += [f'{k}={v}' for k, v in pendientes.items()]
    ruta.write_text('\n'.join(nuevas) + '\n', encoding='utf-8')
    for clave, valor in valores.items():
        os.environ[clave] = str(valor)


def _respaldar_archivo(ruta: Path) -> None:
    if ruta.exists():
        ruta.replace(ruta.with_suffix(ruta.suffix + '.anterior'))
        for extra in ('-wal', '-shm'):
            Path(f'{ruta}{extra}').unlink(missing_ok=True)


def migrar_a_postgres(datos: DatosPostgres, informar=print) -> list[str]:
    if connections['default'].vendor == 'postgresql':
        return ['La base ya está en PostgreSQL.']
    probar_conexion(datos)
    crear_base_si_no_existe(datos)
    registrar_alias(ALIAS_DESTINO, configuracion_postgres(datos))
    try:
        copiar_datos('default', ALIAS_DESTINO)
    finally:
        quitar_alias(ALIAS_DESTINO)
    # La contraseña vive solo en .env (nunca en la base ni en el repositorio).
    actualizar_env({'DB_MOTOR': 'postgres', 'DB_NOMBRE': _nombre_seguro(datos.nombre), 'DB_USUARIO': datos.usuario,
                    'DB_CONTRASENA': datos.contrasena, 'DB_SERVIDOR': datos.servidor, 'DB_PUERTO': datos.puerto})
    resumen = [f'Datos copiados a PostgreSQL ({_nombre_seguro(datos.nombre)}). Reinicie el sistema (start restart) para usarla.',
               'Hágalo fuera del horario de uso: lo que se cargue entre la copia y el reinicio no se copia.']
    for linea in resumen:
        informar(linea)
    return resumen


def _copiar_a_sqlite(cambiar_motor: bool, informar=print) -> list[str]:
    if connections['default'].vendor == 'sqlite':
        return ['La base ya está en SQLite.']
    ruta = Path(settings.DIR_DATOS) / 'aguateras.sqlite3'
    _respaldar_archivo(ruta)
    registrar_alias(ALIAS_DESTINO, configuracion_sqlite(ruta))
    try:
        copiar_datos('default', ALIAS_DESTINO)
    finally:
        quitar_alias(ALIAS_DESTINO)
    if cambiar_motor:
        actualizar_env({'DB_MOTOR': 'sqlite'})
        resumen = ['Datos copiados a SQLite. Reinicie el sistema (start restart) para usarla.']
    else:
        resumen = [f'Datos copiados a {ruta.name} (el sistema sigue usando PostgreSQL). Ya puede generar el backup.']
    for linea in resumen:
        informar(linea)
    return resumen


def volver_a_sqlite(informar=print) -> list[str]:
    return _copiar_a_sqlite(cambiar_motor=True, informar=informar)


def traer_datos_a_sqlite(informar=print) -> list[str]:
    return _copiar_a_sqlite(cambiar_motor=False, informar=informar)


def estado_actual() -> dict:
    cfg = connections['default'].settings_dict
    return {
        'motor': 'PostgreSQL' if connections['default'].vendor == 'postgresql' else 'SQLite',
        'base': Path(str(cfg['NAME'])).name if connections['default'].vendor == 'sqlite' else cfg['NAME'],
        'servidor': cfg.get('HOST') or '',
    }
