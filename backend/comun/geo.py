"""
Datos geográficos en GeoJSON (decisión D1: SQLite en desarrollo; PostGIS solo en producción).

Las coordenadas se guardan como decimales (latitud/longitud, WGS84) y los polígonos de zonas y barrios
como GeoJSON (`Polygon` o `MultiPolygon`). Acá se validan y se hace el cálculo «punto dentro de
polígono» que alcanza para el volumen de una aguatera; con PostGIS se podrá pasar a consultas espaciales.
"""
from decimal import Decimal

from .errores import ErrorNegocio

# Paraguay y alrededores, con margen: atrapa coordenadas invertidas (lat ↔ lon) o en cero.
LIMITES = {'lat': (-28.5, -18.5), 'lon': (-63.5, -53.5)}


def validar_coordenadas(latitud, longitud, *, estricto_paraguay: bool = True) -> None:
    if latitud is None and longitud is None:
        return
    if latitud is None or longitud is None:
        raise ErrorNegocio('Indique latitud y longitud, o ninguna de las dos.')
    lat, lon = float(latitud), float(longitud)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ErrorNegocio('Coordenadas fuera de rango.')
    if estricto_paraguay and not (LIMITES['lat'][0] <= lat <= LIMITES['lat'][1]
                                  and LIMITES['lon'][0] <= lon <= LIMITES['lon'][1]):
        raise ErrorNegocio('Las coordenadas no corresponden a Paraguay. ¿Están invertidas latitud y longitud?')


def _anillo_valido(anillo) -> bool:
    if not isinstance(anillo, list) or len(anillo) < 4:
        return False
    for punto in anillo:
        if (not isinstance(punto, (list, tuple)) or len(punto) < 2
                or not all(isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) for v in punto[:2])):
            return False
        if not (-180 <= punto[0] <= 180 and -90 <= punto[1] <= 90):
            return False
    return list(anillo[0][:2]) == list(anillo[-1][:2])


def validar_poligono(geometria) -> dict | None:
    """Acepta None, un GeoJSON Polygon/MultiPolygon o una Feature que lo contenga. Devuelve la geometría."""
    if geometria in (None, '', {}):
        return None
    if isinstance(geometria, dict) and geometria.get('type') == 'Feature':
        geometria = geometria.get('geometry')
    if not isinstance(geometria, dict):
        raise ErrorNegocio('El polígono debe ser GeoJSON.')
    tipo, coords = geometria.get('type'), geometria.get('coordinates')
    if tipo == 'Polygon':
        poligonos = [coords]
    elif tipo == 'MultiPolygon' and isinstance(coords, list):
        poligonos = coords
    else:
        raise ErrorNegocio('El polígono debe ser de tipo Polygon o MultiPolygon.')
    if not poligonos or not all(isinstance(p, list) and p and all(_anillo_valido(a) for a in p) for p in poligonos):
        raise ErrorNegocio('Polígono inválido: cada anillo necesita al menos 3 puntos y cerrar en el punto inicial.')
    return {'type': tipo, 'coordinates': coords}


def _en_anillo(lon: float, lat: float, anillo) -> bool:
    dentro = False
    j = len(anillo) - 1
    for i in range(len(anillo)):
        xi, yi = anillo[i][0], anillo[i][1]
        xj, yj = anillo[j][0], anillo[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-15) + xi:
            dentro = not dentro
        j = i
    return dentro


def punto_en_poligono(latitud, longitud, geometria) -> bool:
    if geometria is None or latitud is None or longitud is None:
        return False
    lat, lon = float(latitud), float(longitud)
    poligonos = [geometria['coordinates']] if geometria['type'] == 'Polygon' else geometria['coordinates']
    for poligono in poligonos:
        exterior, huecos = poligono[0], poligono[1:]
        if _en_anillo(lon, lat, exterior) and not any(_en_anillo(lon, lat, h) for h in huecos):
            return True
    return False


def distancia_metros(lat1, lon1, lat2, lon2) -> int:
    """Distancia aproximada (haversine) entre dos puntos, en metros."""
    from math import asin, cos, radians, sin, sqrt

    p1, p2 = radians(float(lat1)), radians(float(lat2))
    dlat, dlon = p2 - p1, radians(float(lon2) - float(lon1))
    h = sin(dlat / 2) ** 2 + cos(p1) * cos(p2) * sin(dlon / 2) ** 2
    return round(2 * 6_371_000 * asin(sqrt(h)))
