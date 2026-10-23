import { useEffect, useRef, useState } from 'react'
import { L, useMapa } from './leaflet'

export interface Ubicacion {
  latitud: string
  longitud: string
  metodo_ubicacion: 'sin_ubicacion' | 'gps' | 'mapa' | 'manual'
  precision_metros: number | null
}

/**
 * Ubicación de una conexión: clic en el mapa, GPS del teléfono o coordenadas a mano.
 * El GPS del navegador solo funciona con HTTPS (o en la misma computadora): se avisa si no está disponible.
 */
export function SelectorUbicacion({ valor, alCambiar }: { valor: Ubicacion; alCambiar: (u: Ubicacion) => void }) {
  const { ref, mapa } = useMapa({ zoom: 15 })
  const [aviso, setAviso] = useState('')
  const [buscando, setBuscando] = useState(false)
  const centrado = useRef(false)
  const lat = Number(valor.latitud)
  const lon = Number(valor.longitud)
  const hay = valor.latitud !== '' && valor.longitud !== '' && !Number.isNaN(lat) && !Number.isNaN(lon)

  useEffect(() => {
    if (!mapa || !hay) return
    const punto = L.circleMarker([lat, lon], { radius: 9, color: '#EA284E', fillOpacity: 0.8 }).addTo(mapa)
    if (!centrado.current) {
      mapa.setView([lat, lon], 17)
      centrado.current = true
    }
    return () => {
      punto.remove()
    }
  }, [mapa, hay, lat, lon])

  useEffect(() => {
    if (!mapa) return
    const alClic = (e: L.LeafletMouseEvent) =>
      alCambiar({ latitud: e.latlng.lat.toFixed(6), longitud: e.latlng.lng.toFixed(6), metodo_ubicacion: 'mapa', precision_metros: null })
    mapa.on('click', alClic)
    return () => {
      mapa.off('click', alClic)
    }
  }, [mapa, alCambiar])

  function usarGps() {
    setAviso('')
    if (!window.isSecureContext || !navigator.geolocation) {
      setAviso('El GPS del navegador necesita HTTPS. Marque el punto en el mapa o cargue las coordenadas.')
      return
    }
    setBuscando(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setBuscando(false)
        centrado.current = false
        alCambiar({
          latitud: pos.coords.latitude.toFixed(6), longitud: pos.coords.longitude.toFixed(6), metodo_ubicacion: 'gps',
          precision_metros: Math.round(pos.coords.accuracy),
        })
      },
      (error) => {
        setBuscando(false)
        setAviso(error.code === error.PERMISSION_DENIED ? 'No se dio permiso para usar la ubicación.' : 'No se pudo obtener la ubicación.')
      },
      { enableHighAccuracy: true, timeout: 20_000 },
    )
  }

  return (
    <div className="space-y-2">
      <div ref={ref} className="h-72 w-full overflow-hidden rounded-lg border border-koape-gris-claro" />
      <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto_auto]">
        <input className="campo" placeholder="Latitud (ej. -25.2867)" value={valor.latitud}
          onChange={(e) => alCambiar({ ...valor, latitud: e.target.value.trim(), metodo_ubicacion: 'manual', precision_metros: null })} />
        <input className="campo" placeholder="Longitud (ej. -57.6470)" value={valor.longitud}
          onChange={(e) => alCambiar({ ...valor, longitud: e.target.value.trim(), metodo_ubicacion: 'manual', precision_metros: null })} />
        <button type="button" className="boton-secundario" onClick={usarGps} disabled={buscando}>{buscando ? 'Buscando…' : 'Usar GPS'}</button>
        <button type="button" className="boton-secundario" disabled={!hay}
          onClick={() => alCambiar({ latitud: '', longitud: '', metodo_ubicacion: 'sin_ubicacion', precision_metros: null })}>Quitar</button>
      </div>
      <p className="text-xs text-koape-gris">
        Haga clic en el mapa sobre la vivienda, use el GPS del teléfono o escriba las coordenadas.
        {valor.precision_metros ? ` Precisión del GPS: ${valor.precision_metros} m.` : ''}
      </p>
      {aviso && <p className="text-xs font-semibold text-koape-rojo">{aviso}</p>}
    </div>
  )
}
