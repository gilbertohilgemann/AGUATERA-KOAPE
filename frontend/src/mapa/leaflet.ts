/**
 * Utilidades de mapa (Leaflet + OpenStreetMap).
 *
 * GeoJSON guarda [longitud, latitud]; Leaflet usa [latitud, longitud]: toda conversión pasa por acá.
 * Se usan círculos (circleMarker) en vez de íconos: no dependen de imágenes que el empaquetador pierde.
 */
import { useEffect, useRef, useState } from 'react'
import * as L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { EstadoConexion, Poligono } from '../api/tipos'

/** Asunción. Al cargar datos, el mapa se ajusta solo a las conexiones y zonas de la institución. */
export const CENTRO_INICIAL: L.LatLngTuple = [-25.2867, -57.647]

export const COLOR_ESTADO: Record<EstadoConexion, string> = {
  activa: '#16A34A',
  en_instalacion: '#2563EB',
  pendiente_ubicacion: '#F9C610',
  suspendida: '#EA580C',
  desconectada: '#DC2626',
  archivada: '#97989C',
}

export const NOMBRE_ESTADO: Record<EstadoConexion, string> = {
  activa: 'Activa',
  en_instalacion: 'En instalación',
  pendiente_ubicacion: 'Pendiente de ubicación',
  suspendida: 'Suspendida',
  desconectada: 'Desconectada',
  archivada: 'Archivada',
}

/** Crea el mapa sobre un <div> y lo destruye al desmontar. */
export function useMapa(opciones: { zoom?: number } = {}) {
  const ref = useRef<HTMLDivElement>(null)
  const [mapa, setMapa] = useState<L.Map | null>(null)
  const zoom = opciones.zoom ?? 13
  useEffect(() => {
    if (!ref.current) return
    const m = L.map(ref.current, { center: CENTRO_INICIAL, zoom })
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(m)
    setMapa(m)
    // Si el contenedor cambia de tamaño (menú del celular, modal) el mapa se vuelve a medir.
    const observador = new ResizeObserver(() => m.invalidateSize())
    observador.observe(ref.current)
    return () => {
      observador.disconnect()
      m.remove()
      setMapa(null)
    }
  }, [zoom])
  return { ref, mapa }
}

export function aLatLngs(poligono: Poligono): L.LatLngExpression[][][] {
  const anillos = (p: number[][][]) => p.map((anillo) => anillo.map(([lon, lat]) => [lat, lon] as L.LatLngTuple))
  return poligono.type === 'Polygon' ? [anillos(poligono.coordinates)] : poligono.coordinates.map(anillos)
}

export function capaPoligono(poligono: Poligono, color: string, opciones: L.PolylineOptions = {}): L.Polygon {
  return L.polygon(aLatLngs(poligono), { color, weight: 2, fillOpacity: 0.12, ...opciones })
}

/** Texto plano en un elemento (nunca HTML armado con datos: evita inyectar código en los popups). */
export function elemento(etiqueta: string, texto: string, clase = ''): HTMLElement {
  const nodo = document.createElement(etiqueta)
  nodo.textContent = texto
  if (clase) nodo.className = clase
  return nodo
}

export { L }
