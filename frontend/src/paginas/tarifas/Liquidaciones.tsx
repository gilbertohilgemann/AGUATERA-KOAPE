import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { mensajeDeError } from '../../api/cliente'
import type { Liquidacion, Pagina, ResumenLiquidaciones } from '../../api/tipos'
import { Aviso } from '../../componentes/Aviso'
import { Campo } from '../../componentes/Campo'
import { Encabezado } from '../../componentes/Encabezado'
import { Paginador } from '../../componentes/Paginador'
import { useSesion } from '../../sesion/ContextoSesion'
import { fechaHora } from '../../utilidades/fechas'
import { periodoActual } from '../lecturas/Recorridos'
import { TablaCalculo, gs, num } from './Tarifas'

export function Liquidaciones() {
  const { api, puede } = useSesion()
  const [filtros, setFiltros] = useState({ periodo: periodoActual(), estado: 'vigente', buscar: '', tarifa: '' })
  const [pagina, setPagina] = useState(1)
  const [datos, setDatos] = useState<Pagina<Liquidacion> | null>(null)
  const [resumen, setResumen] = useState<ResumenLiquidaciones | null>(null)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')

  const cargar = useCallback(async () => {
    try {
      const params = Object.fromEntries(Object.entries({ ...filtros, pagina }).filter(([, v]) => v !== ''))
      const [l, r] = await Promise.all([
        api.get<Pagina<Liquidacion>>('liquidaciones/', { params }),
        api.get<ResumenLiquidaciones>('liquidaciones-resumen/', { params: { periodo: filtros.periodo || undefined } }),
      ])
      setDatos(l.data)
      setResumen(r.data)
      setError('')
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }, [api, filtros, pagina])

  useEffect(() => {
    const t = setTimeout(() => void cargar(), 250)
    return () => clearTimeout(t)
  }, [cargar])

  async function liquidarPendientes() {
    setAviso('')
    setError('')
    try {
      const r = await api.post<{ liquidadas: string[]; sin_tarifa: string[] }>('liquidaciones/liquidar-pendientes/', { periodo: filtros.periodo || null })
      setAviso(`${r.data.liquidadas.length} lectura(s) liquidada(s).${r.data.sin_tarifa.length ? ` ${r.data.sin_tarifa.length} siguen sin tarifa vigente: revise Tarifas.` : ''}`)
      await cargar()
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }

  const filtrar = (c: Partial<typeof filtros>) => { setPagina(1); setFiltros({ ...filtros, ...c }) }

  return (
    <div>
      <Encabezado titulo="Liquidaciones" descripcion="Importe de cada lectura confirmada según la tarifa vigente en su período. Se generan solas al confirmarse la lectura." />
      <Aviso tipo="error">{error}</Aviso>
      <Aviso tipo="exito">{aviso}</Aviso>
      {resumen && (
        <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="tarjeta p-4"><p className="etiqueta">Liquidaciones vigentes</p><p className="text-2xl font-extrabold">{resumen.cantidad}</p><p className="text-xs text-koape-gris">{num(resumen.consumo)} m³</p></div>
          <div className="tarjeta p-4"><p className="etiqueta">Gravado + IVA</p><p className="text-sm">10 %: {gs(resumen.gravado10)} + {gs(resumen.iva10)}</p><p className="text-sm">5 %: {gs(resumen.gravado5)} + {gs(resumen.iva5)}</p></div>
          <div className="tarjeta p-4"><p className="etiqueta">Exento</p><p className="text-xl font-bold">{gs(resumen.exento)}</p></div>
          <div className="tarjeta p-4"><p className="etiqueta">Total del período</p><p className="text-2xl font-extrabold">{gs(resumen.total)}</p></div>
        </div>
      )}
      {resumen && resumen.sin_liquidar > 0 && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          <span><b>{resumen.sin_liquidar}</b> lectura(s) confirmada(s) sin liquidar (no había tarifa vigente o estaba mal configurada).</span>
          {puede('tarifas.gestionar') && <button className="boton-secundario" onClick={() => void liquidarPendientes()}>Liquidar pendientes</button>}
        </div>
      )}
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Campo etiqueta="Período"><input type="month" className="campo" value={filtros.periodo} onChange={(e) => filtrar({ periodo: e.target.value })} /></Campo>
        <Campo etiqueta="Estado">
          <select className="campo" value={filtros.estado} onChange={(e) => filtrar({ estado: e.target.value })}>
            <option value="vigente">Vigentes</option><option value="anulada">Anuladas</option><option value="">Todas</option>
          </select>
        </Campo>
        <Campo etiqueta="Buscar"><input className="campo" placeholder="Número, conexión o titular" value={filtros.buscar} onChange={(e) => filtrar({ buscar: e.target.value })} /></Campo>
        <Campo etiqueta="Tarifa (código)"><input className="campo uppercase" value={filtros.tarifa} onChange={(e) => filtrar({ tarifa: e.target.value })} /></Campo>
      </div>
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Número</th><th>Conexión</th><th>Titular</th><th>Tarifa</th><th>Consumo</th><th className="text-right">Total</th><th>Estado</th></tr></thead>
          <tbody>
            {datos?.results.map((q) => (
              <tr key={q.numero} className={q.estado === 'anulada' ? 'text-koape-gris' : ''}>
                <td><Link className="font-semibold text-koape-rojo hover:underline" to={`/panel/liquidaciones/${q.numero}`}>{q.numero}</Link></td>
                <td>{q.conexion}</td>
                <td>{q.titular}</td>
                <td>{q.tarifa_nombre}</td>
                <td>{num(q.consumo)} m³</td>
                <td className="text-right font-semibold">{gs(q.total)}</td>
                <td>{q.estado_nombre}</td>
              </tr>
            ))}
            {datos?.results.length === 0 && <tr><td colSpan={7} className="text-center text-koape-gris">Sin liquidaciones.</td></tr>}
          </tbody>
        </table>
      </div>
      {datos && <Paginador pagina={pagina} total={datos.count} alCambiar={setPagina} />}
    </div>
  )
}

export function FichaLiquidacion() {
  const { numero = '' } = useParams()
  const { api } = useSesion()
  const [q, setQ] = useState<Liquidacion | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    api.get<Liquidacion>(`liquidaciones/${encodeURIComponent(numero)}/`).then((r) => setQ(r.data)).catch((e) => setError(mensajeDeError(e)))
  }, [api, numero])
  if (!q) return error ? <Aviso tipo="error">{error}</Aviso> : <p className="text-koape-gris">Cargando…</p>
  return (
    <div className="max-w-4xl space-y-4">
      <div>
        <p className="text-sm"><Link className="text-koape-rojo hover:underline" to="/panel/liquidaciones">← Liquidaciones</Link></p>
        <h1 className="text-2xl font-extrabold">Liquidación {q.numero}</h1>
        <p className="text-sm text-koape-gris">Período {q.periodo} · {q.estado_nombre} · calculada {fechaHora(q.creado_en)}</p>
      </div>
      {q.estado === 'anulada' && <Aviso tipo="error">Anulada {fechaHora(q.anulada_en)}{q.anulada_por ? ` por ${q.anulada_por}` : ''}: {q.motivo_anulacion}</Aviso>}
      <section className="tarjeta p-5">
        <dl className="grid gap-3 text-sm sm:grid-cols-3">
          <div><dt className="etiqueta">Conexión</dt><dd><Link className="font-semibold text-koape-rojo hover:underline" to={`/panel/conexiones/${q.conexion}`}>{q.conexion}</Link> · {q.titular}</dd></div>
          <div><dt className="etiqueta">Lectura</dt><dd><Link className="text-koape-rojo hover:underline" to={`/panel/lecturas/${q.lectura}`}>{q.lectura}</Link> · {num(q.consumo)} m³</dd></div>
          <div><dt className="etiqueta">Tarifa</dt><dd>{q.tarifa_nombre} ({q.tarifa}) · versión desde {q.version}</dd></div>
        </dl>
      </section>
      <section className="tarjeta p-5"><TablaCalculo r={q} /></section>
      <p className="text-xs text-koape-gris">Los importes y precios son los vigentes al calcular: si la tarifa cambia después, esta liquidación no se modifica.</p>
    </div>
  )
}
