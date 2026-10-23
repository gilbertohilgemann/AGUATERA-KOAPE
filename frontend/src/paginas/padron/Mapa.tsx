import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { mensajeDeError } from '../../api/cliente'
import type { DatosMapa, EstadoConexion, Poligono } from '../../api/tipos'
import { Aviso } from '../../componentes/Aviso'
import { Campo } from '../../componentes/Campo'
import { COLOR_ESTADO, L, NOMBRE_ESTADO, capaPoligono, elemento, useMapa } from '../../mapa/leaflet'
import { useSesion } from '../../sesion/ContextoSesion'

type Colorear = 'estado' | 'zona' | 'deuda'

/** Definiciones explícitas (D50): con deuda = consumo sin facturar o factura a crédito con saldo; morosa = alguna
 * factura a crédito vencida con saldo. */
const DEUDA: Record<string, [string, string]> = {
  al_dia: ['Al día', '#16A34A'], con: ['Con deuda (sin vencer)', '#F59E0B'], morosa: ['Morosa (factura vencida)', '#DC2626'],
}

/**
 * Mapa de conexiones (sección 8.2): zonas con sus colores y polígonos, conexiones con su estado,
 * ficha al tocar un punto y filtros combinables: estado, zona, barrio, lectura del período, recorrido, cobrador y
 * deuda (con deuda, al día, morosa; solo con permiso de cobranzas o facturas).
 */
export function Mapa() {
  const { api, puede } = useSesion()
  const veDeuda = puede('cobranzas.consultar') || puede('facturacion.consultar')
  const navegar = useNavigate()
  const { ref, mapa } = useMapa()
  const [datos, setDatos] = useState<DatosMapa | null>(null)
  const [filtros, setFiltros] = useState({ buscar: '', zona: '', barrio: '', sin_medidor: false, lectura: '', periodo: new Date().toLocaleDateString('en-CA').slice(0, 7), recorrido: '', cobrador: '', deuda: '' })
  const [estados, setEstados] = useState<EstadoConexion[]>([])
  const [colorear, setColorear] = useState<Colorear>('estado')
  const [error, setError] = useState('')
  const ajustado = useRef(false)

  useEffect(() => {
    const temporizador = setTimeout(() => {
      api.get<DatosMapa>('mapa/', {
        params: {
          buscar: filtros.buscar || undefined, zona: filtros.zona || undefined, barrio: filtros.barrio || undefined,
          sin_medidor: filtros.sin_medidor ? 1 : undefined, estado: estados.length ? estados.join(',') : undefined,
          lectura: filtros.lectura || undefined, periodo: filtros.lectura ? filtros.periodo : undefined,
          recorrido: filtros.recorrido || undefined, cobrador: filtros.cobrador || undefined,
          deuda: filtros.deuda || undefined,
        },
      }).then((r) => { setDatos(r.data); setError('') }).catch((e) => setError(mensajeDeError(e)))
    }, 250)
    return () => clearTimeout(temporizador)
  }, [api, filtros, estados])

  useEffect(() => {
    if (!mapa || !datos) return
    const capas = L.layerGroup().addTo(mapa)
    const colorZona = new Map(datos.zonas.map((z) => [z.Code, z.color]))
    const limites = L.latLngBounds([])
    datos.zonas.filter((z) => z.poligono && z.activa).forEach((z) => {
      const capa = capaPoligono(z.poligono as Poligono, z.color).bindTooltip(elemento('span', z.nombre), { sticky: true }).addTo(capas)
      limites.extend(capa.getBounds())
    })
    datos.barrios.filter((b) => b.poligono && b.activo).forEach((b) => {
      capaPoligono(b.poligono as Poligono, b.color, { weight: 1, fillOpacity: 0.04, dashArray: '3 3' }).bindTooltip(elemento('span', b.nombre), { sticky: true }).addTo(capas)
    })
    datos.conexiones.forEach((c) => {
      const color = colorear === 'zona' ? (c.zona ? colorZona.get(c.zona) ?? '#97989C' : '#97989C')
        : colorear === 'deuda' ? (c.deuda ? DEUDA[c.deuda][1] : '#97989C') : COLOR_ESTADO[c.estado]
      const ficha = document.createElement('div')
      ficha.className = 'text-sm'
      ficha.append(
        elemento('div', `Conexión ${c.Code}`, 'font-bold'),
        elemento('div', c.titular),
        elemento('div', c.direccion || 'Sin dirección', 'text-xs'),
        elemento('div', `${c.barrio || 'Sin barrio'} · ${c.estado_nombre}`, 'text-xs'),
        elemento('div', c.medidor ? `Medidor ${c.medidor}` : 'Sin medidor', 'text-xs'),
      )
      if (c.deuda) ficha.append(elemento('div', DEUDA[c.deuda][0], 'text-xs font-semibold'))
      const abrir = elemento('button', 'Abrir ficha', 'mt-2 font-semibold text-koape-rojo underline')
      abrir.addEventListener('click', () => navegar(`/panel/conexiones/${c.Code}`))
      ficha.append(abrir)
      L.circleMarker([c.lat, c.lon], { radius: 7, color: '#FFFFFF', weight: 2, fillColor: color, fillOpacity: 0.95 })
        .bindPopup(ficha).addTo(capas)
      limites.extend([c.lat, c.lon])
    })
    if (!ajustado.current && limites.isValid()) {
      mapa.fitBounds(limites, { padding: [30, 30], maxZoom: 17 })
      ajustado.current = true
    }
    return () => {
      capas.remove()
    }
  }, [mapa, datos, colorear, navegar])

  const alternarEstado = (e: EstadoConexion) => setEstados(estados.includes(e) ? estados.filter((x) => x !== e) : [...estados, e])
  const barrios = datos?.barrios.filter((b) => !filtros.zona || b.zona === filtros.zona) ?? []

  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-extrabold">Mapa</h1>
      <Aviso tipo="error">{error}</Aviso>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Campo etiqueta="Buscar"><input className="campo" placeholder="Código, titular, medidor…" value={filtros.buscar} onChange={(e) => setFiltros({ ...filtros, buscar: e.target.value })} /></Campo>
        <Campo etiqueta="Zona">
          <select className="campo" value={filtros.zona} onChange={(e) => setFiltros({ ...filtros, zona: e.target.value, barrio: '' })}>
            <option value="">Todas</option>
            {datos?.zonas.map((z) => <option key={z.Code} value={z.Code}>{z.nombre}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Barrio">
          <select className="campo" value={filtros.barrio} onChange={(e) => setFiltros({ ...filtros, barrio: e.target.value })}>
            <option value="">Todos</option>
            {barrios.map((b) => <option key={b.Code} value={b.Code}>{b.nombre}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Colorear por">
          <select className="campo" value={colorear} onChange={(e) => setColorear(e.target.value as Colorear)}>
            <option value="estado">Estado de la conexión</option><option value="zona">Zona</option>
            {veDeuda && <option value="deuda">Deuda</option>}
          </select>
        </Campo>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {(Object.keys(NOMBRE_ESTADO) as EstadoConexion[]).map((e) => (
          <button key={e} type="button" onClick={() => alternarEstado(e)}
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-semibold ${estados.includes(e) ? 'border-koape-tinta bg-koape-tinta text-white' : 'border-koape-gris-claro bg-white'}`}>
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: COLOR_ESTADO[e] }} />{NOMBRE_ESTADO[e]}
          </button>
        ))}
        <label className="ml-2 flex items-center gap-1.5"><input type="checkbox" checked={filtros.sin_medidor} onChange={(e) => setFiltros({ ...filtros, sin_medidor: e.target.checked })} /> Sin medidor</label>
      </div>
      <div className="flex flex-wrap items-end gap-3 text-sm">
        <Campo etiqueta="Lectura del período">
          <select className="campo" value={filtros.lectura} onChange={(e) => setFiltros({ ...filtros, lectura: e.target.value })}>
            <option value="">Con y sin lectura</option><option value="con">Con lectura</option><option value="sin">Sin lectura</option>
          </select>
        </Campo>
        {filtros.lectura && <Campo etiqueta="Período"><input type="month" className="campo" value={filtros.periodo} onChange={(e) => setFiltros({ ...filtros, periodo: e.target.value })} /></Campo>}
        <Campo etiqueta="Recorrido (código)"><input className="campo uppercase" value={filtros.recorrido} onChange={(e) => setFiltros({ ...filtros, recorrido: e.target.value })} /></Campo>
        <Campo etiqueta="Cobrador (usuario)"><input className="campo" value={filtros.cobrador} onChange={(e) => setFiltros({ ...filtros, cobrador: e.target.value })} /></Campo>
        {veDeuda && (
          <Campo etiqueta="Deuda">
            <select className="campo" value={filtros.deuda} onChange={(e) => setFiltros({ ...filtros, deuda: e.target.value })}>
              <option value="">Todas</option><option value="con">Con deuda</option><option value="al_dia">Al día</option>
              <option value="morosa">Morosas (factura vencida)</option><option value="sin_facturar">Con consumo sin facturar</option>
            </select>
          </Campo>
        )}
      </div>
      {colorear === 'deuda' && (
        <div className="flex flex-wrap gap-3 text-xs">
          {Object.entries(DEUDA).map(([k, [t, c]]) => <span key={k} className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: c }} />{t}</span>)}
        </div>
      )}
      <div ref={ref} className="h-[65vh] w-full overflow-hidden rounded-xl border border-koape-gris-claro" />
      {datos && (
        <p className="text-sm text-koape-gris">
          {datos.conexiones.length} en el mapa de {datos.total} conexiones filtradas
          {datos.sin_ubicacion > 0 && <> · <b className="text-koape-rojo">{datos.sin_ubicacion} sin ubicación</b> (búsquelas en Conexiones con el filtro «Sin ubicación»)</>}
        </p>
      )}
    </div>
  )
}
