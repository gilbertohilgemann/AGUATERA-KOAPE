import { useEffect, useRef, useState } from 'react'
import type { Poligono } from '../api/tipos'
import { L, aLatLngs, capaPoligono, elemento, useMapa } from './leaflet'

interface Contexto {
  poligono: Poligono | null
  color: string
  nombre: string
}

/**
 * Dibuja o redibuja el polígono de una zona o barrio: «Dibujar», un clic por vértice y «Terminar».
 * Los polígonos de las demás zonas se ven de fondo para no superponerlas sin querer.
 */
export function EditorPoligono({ valor, color, alCambiar, contexto = [] }: {
  valor: Poligono | null
  color: string
  alCambiar: (p: Poligono | null) => void
  contexto?: Contexto[]
}) {
  const { ref, mapa } = useMapa()
  const [dibujando, setDibujando] = useState(false)
  const [puntos, setPuntos] = useState<L.LatLng[]>([])
  const ajustado = useRef(false)

  // Fondo: las otras zonas/barrios.
  useEffect(() => {
    if (!mapa) return
    const grupo = L.layerGroup(
      contexto.filter((c) => c.poligono).map((c) =>
        capaPoligono(c.poligono as Poligono, c.color, { weight: 1, fillOpacity: 0.05, dashArray: '4 4' }).bindTooltip(elemento('span', c.nombre))),
    ).addTo(mapa)
    return () => {
      grupo.remove()
    }
  }, [mapa, contexto])

  // El polígono actual (o el que se está dibujando).
  useEffect(() => {
    if (!mapa) return
    const grupo = L.layerGroup().addTo(mapa)
    if (dibujando) {
      if (puntos.length) L.polyline(puntos, { color, dashArray: '6 4' }).addTo(grupo)
      puntos.forEach((p) => L.circleMarker(p, { radius: 4, color }).addTo(grupo))
    } else if (valor) {
      const capa = capaPoligono(valor, color).addTo(grupo)
      if (!ajustado.current) {
        mapa.fitBounds(capa.getBounds(), { padding: [20, 20] })
        ajustado.current = true
      }
    } else if (!ajustado.current) {
      const conPoligono = contexto.filter((c) => c.poligono)
      if (conPoligono.length) {
        const limites = L.latLngBounds([])
        conPoligono.forEach((c) => limites.extend(L.polygon(aLatLngs(c.poligono as Poligono)).getBounds()))
        mapa.fitBounds(limites, { padding: [20, 20] })
        ajustado.current = true
      }
    }
    return () => {
      grupo.remove()
    }
  }, [mapa, valor, color, dibujando, puntos, contexto])

  useEffect(() => {
    if (!mapa || !dibujando) return
    const alClic = (e: L.LeafletMouseEvent) => setPuntos((ps) => [...ps, e.latlng])
    mapa.on('click', alClic)
    mapa.getContainer().style.cursor = 'crosshair'
    return () => {
      mapa.off('click', alClic)
      mapa.getContainer().style.cursor = ''
    }
  }, [mapa, dibujando])

  function terminar() {
    if (puntos.length < 3) return
    const anillo = puntos.map((p) => [Number(p.lng.toFixed(6)), Number(p.lat.toFixed(6))])
    anillo.push([...anillo[0]])
    alCambiar({ type: 'Polygon', coordinates: [anillo] })
    setPuntos([])
    setDibujando(false)
  }

  return (
    <div className="space-y-2">
      <div ref={ref} className="h-80 w-full overflow-hidden rounded-lg border border-koape-gris-claro" />
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {!dibujando ? (
          <>
            <button type="button" className="boton-secundario" onClick={() => { setPuntos([]); setDibujando(true) }}>
              {valor ? 'Redibujar' : 'Dibujar polígono'}
            </button>
            {valor && <button type="button" className="boton-secundario" onClick={() => alCambiar(null)}>Quitar polígono</button>}
          </>
        ) : (
          <>
            <span className="text-koape-gris">Haga clic en el mapa en cada esquina ({puntos.length} puntos).</span>
            <button type="button" className="boton-secundario" disabled={!puntos.length} onClick={() => setPuntos(puntos.slice(0, -1))}>Deshacer punto</button>
            <button type="button" className="boton-primario" disabled={puntos.length < 3} onClick={terminar}>Terminar</button>
            <button type="button" className="boton-secundario" onClick={() => { setPuntos([]); setDibujando(false) }}>Cancelar</button>
          </>
        )}
      </div>
    </div>
  )
}
