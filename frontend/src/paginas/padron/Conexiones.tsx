import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { mensajeDeError } from '../../api/cliente'
import type { Barrio, ConexionResumen, EstadoConexion, Pagina, Zona } from '../../api/tipos'
import { Aviso } from '../../componentes/Aviso'
import { Campo } from '../../componentes/Campo'
import { Encabezado } from '../../componentes/Encabezado'
import { Paginador } from '../../componentes/Paginador'
import { COLOR_ESTADO, NOMBRE_ESTADO } from '../../mapa/leaflet'
import { useSesion } from '../../sesion/ContextoSesion'

export function InsigniaEstado({ estado, nombre }: { estado: EstadoConexion; nombre?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-semibold"
      style={{ background: `${COLOR_ESTADO[estado]}22`, color: COLOR_ESTADO[estado] }}>
      <span className="h-2 w-2 rounded-full" style={{ background: COLOR_ESTADO[estado] }} />{nombre ?? NOMBRE_ESTADO[estado]}
    </span>
  )
}

export function useTerritorio() {
  const { api } = useSesion()
  const [zonas, setZonas] = useState<Zona[]>([])
  const [barrios, setBarrios] = useState<Barrio[]>([])
  useEffect(() => {
    api.get<Zona[]>('zonas/').then((r) => setZonas(r.data)).catch(() => setZonas([]))
    api.get<Barrio[]>('barrios/').then((r) => setBarrios(r.data)).catch(() => setBarrios([]))
  }, [api])
  return { zonas, barrios }
}

export function Conexiones() {
  const { api, puede } = useSesion()
  const { zonas, barrios } = useTerritorio()
  const [conexiones, setConexiones] = useState<ConexionResumen[]>([])
  const [total, setTotal] = useState(0)
  const [pagina, setPagina] = useState(1)
  const [filtros, setFiltros] = useState({ buscar: '', estado: '', zona: '', barrio: '', ubicacion: '', deuda: '', sin_medidor: false, incluir_archivadas: false })
  const [error, setError] = useState('')

  const cargar = useCallback(async () => {
    try {
      const params = {
        pagina, buscar: filtros.buscar || undefined, estado: filtros.estado || undefined, zona: filtros.zona || undefined,
        barrio: filtros.barrio || undefined, ubicacion: filtros.ubicacion || undefined, sin_medidor: filtros.sin_medidor ? 1 : undefined,
        incluir_archivadas: filtros.incluir_archivadas ? 1 : undefined, deuda: filtros.deuda || undefined,
      }
      const r = await api.get<Pagina<ConexionResumen>>('conexiones/', { params })
      setConexiones(r.data.results)
      setTotal(r.data.count)
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }, [api, filtros, pagina])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const filtrar = (cambio: Partial<typeof filtros>) => { setPagina(1); setFiltros({ ...filtros, ...cambio }) }

  return (
    <div>
      <Encabezado titulo="Conexiones" descripcion="Conexiones de agua, con su titular, ubicación y medidor."
        acciones={puede('padron.conexiones') && <Link className="boton-primario" to="/panel/nueva-conexion">Nueva conexión</Link>} />
      <Aviso tipo="error">{error}</Aviso>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Campo etiqueta="Buscar"><input className="campo" placeholder="Código, titular, documento, medidor…" value={filtros.buscar} onChange={(e) => filtrar({ buscar: e.target.value })} /></Campo>
        <Campo etiqueta="Estado">
          <select className="campo" value={filtros.estado} onChange={(e) => filtrar({ estado: e.target.value })}>
            <option value="">Todos (sin archivadas)</option>
            {Object.entries(NOMBRE_ESTADO).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Zona">
          <select className="campo" value={filtros.zona} onChange={(e) => filtrar({ zona: e.target.value, barrio: '' })}>
            <option value="">Todas</option>
            {zonas.map((z) => <option key={z.Code} value={z.Code}>{z.nombre}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Barrio">
          <select className="campo" value={filtros.barrio} onChange={(e) => filtrar({ barrio: e.target.value })}>
            <option value="">Todos</option>
            {barrios.filter((b) => !filtros.zona || b.zona === filtros.zona).map((b) => <option key={b.Code} value={b.Code}>{b.nombre}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Ubicación">
          <select className="campo" value={filtros.ubicacion} onChange={(e) => filtrar({ ubicacion: e.target.value })}>
            <option value="">Todas</option><option value="con">Con ubicación</option><option value="sin">Sin ubicación</option>
          </select>
        </Campo>
        {(puede('cobranzas.consultar') || puede('facturacion.consultar')) && (
          <Campo etiqueta="Deuda">
            <select className="campo" value={filtros.deuda} onChange={(e) => filtrar({ deuda: e.target.value })}>
              <option value="">Todas</option><option value="con">Con deuda</option><option value="al_dia">Al día</option>
              <option value="morosa">Morosas (factura vencida)</option><option value="sin_facturar">Con consumo sin facturar</option>
            </select>
          </Campo>
        )}
      </div>
      <div className="mb-4 flex flex-wrap gap-4 text-sm text-koape-gris">
        <label className="flex items-center gap-2"><input type="checkbox" checked={filtros.sin_medidor} onChange={(e) => filtrar({ sin_medidor: e.target.checked })} /> Sin medidor</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={filtros.incluir_archivadas} onChange={(e) => filtrar({ incluir_archivadas: e.target.checked })} /> Incluir archivadas</label>
      </div>
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Código</th><th>Titular</th><th>Dirección</th><th>Zona / barrio</th><th>Medidor</th><th>Ubicación</th><th>Estado</th></tr></thead>
          <tbody>
            {conexiones.map((c) => (
              <tr key={c.Code}>
                <td><Link className="font-semibold text-koape-rojo hover:underline" to={`/panel/conexiones/${c.Code}`}>{c.Code}</Link></td>
                <td>{c.cliente_nombre}</td>
                <td>{c.direccion || '—'}</td>
                <td>{c.barrio_nombre ? `${c.zona_nombre} / ${c.barrio_nombre}` : '—'}</td>
                <td>{c.medidor_actual ? <>{c.medidor_actual}{c.medidor_numero && <span className="block font-mono text-xs text-koape-gris">N.º {c.medidor_numero}</span>}</> : <span className="text-koape-gris">Sin medidor</span>}</td>
                <td>{c.latitud ? '✓' : <span className="text-koape-gris">Falta</span>}</td>
                <td><InsigniaEstado estado={c.estado} nombre={c.estado_nombre} /></td>
              </tr>
            ))}
            {conexiones.length === 0 && <tr><td colSpan={7} className="text-center text-koape-gris">Sin resultados.</td></tr>}
          </tbody>
        </table>
      </div>
      <Paginador pagina={pagina} total={total} alCambiar={setPagina} />
    </div>
  )
}
