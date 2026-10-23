import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { mensajeDeError } from '../../api/cliente'
import type { EstadoLectura, Lectura, Liquidacion, Pagina } from '../../api/tipos'
import { Aviso } from '../../componentes/Aviso'
import { Campo } from '../../componentes/Campo'
import { Encabezado } from '../../componentes/Encabezado'
import { FotoPrivada } from '../../componentes/FotoPrivada'
import { Modal } from '../../componentes/Modal'
import { Paginador } from '../../componentes/Paginador'
import { useSesion } from '../../sesion/ContextoSesion'
import { fechaHora } from '../../utilidades/fechas'
import { periodoActual } from './Recorridos'

const COLOR: Record<EstadoLectura, string> = {
  confirmada: 'bg-emerald-100 text-emerald-800', requiere_revision: 'bg-amber-100 text-amber-800', anulada: 'bg-slate-200 text-slate-600',
}

export const numero = (v: string | null | undefined) => (v === null || v === undefined || v === '' ? '—' : Number(v).toLocaleString('es-PY', { maximumFractionDigits: 3 }))

export function InsigniaLectura({ l }: { l: Pick<Lectura, 'estado' | 'estado_nombre'> }) {
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${COLOR[l.estado]}`}>{l.estado_nombre}</span>
}

/** Abre un PDF privado (se pide con el token) en una pestaña nueva. */
export function useAbrirPdf() {
  const { api } = useSesion()
  return async (ruta: string) => {
    const ventana = window.open('', '_blank')
    try {
      const r = await api.get<Blob>(ruta, { responseType: 'blob' })
      const url = URL.createObjectURL(r.data)
      if (ventana) ventana.location.href = url
      else window.location.href = url
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch {
      ventana?.close()
    }
  }
}

export function Lecturas() {
  const { api } = useSesion()
  const [filtros, setFiltros] = useState({ periodo: periodoActual(), estado: '', buscar: '', recorrido: '', cobrador: '' })
  const [pagina, setPagina] = useState(1)
  const [datos, setDatos] = useState<Pagina<Lectura> | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const t = setTimeout(() => {
      const params = Object.fromEntries(Object.entries({ ...filtros, pagina }).filter(([, v]) => v !== ''))
      api.get<Pagina<Lectura>>('lecturas/', { params }).then((r) => { setDatos(r.data); setError('') }).catch((e) => setError(mensajeDeError(e)))
    }, 250)
    return () => clearTimeout(t)
  }, [api, filtros, pagina])

  const filtrar = (c: Partial<typeof filtros>) => { setPagina(1); setFiltros({ ...filtros, ...c }) }

  return (
    <div>
      <Encabezado titulo="Lecturas" descripcion="Lecturas tomadas por los cobradores. Las que requieren revisión se autorizan, corrigen o anulan acá." />
      <Aviso tipo="error">{error}</Aviso>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Campo etiqueta="Período"><input type="month" className="campo" value={filtros.periodo} onChange={(e) => filtrar({ periodo: e.target.value })} /></Campo>
        <Campo etiqueta="Estado">
          <select className="campo" value={filtros.estado} onChange={(e) => filtrar({ estado: e.target.value })}>
            <option value="">Todos</option><option value="requiere_revision">Requiere revisión</option>
            <option value="confirmada">Confirmada</option><option value="anulada">Anulada</option>
          </select>
        </Campo>
        <Campo etiqueta="Buscar"><input className="campo" placeholder="Comprobante, conexión, titular, código o N.º de medidor" value={filtros.buscar} onChange={(e) => filtrar({ buscar: e.target.value })} /></Campo>
        <Campo etiqueta="Recorrido"><input className="campo uppercase" value={filtros.recorrido} onChange={(e) => filtrar({ recorrido: e.target.value })} /></Campo>
        <Campo etiqueta="Cobrador (usuario)"><input className="campo" value={filtros.cobrador} onChange={(e) => filtrar({ cobrador: e.target.value })} /></Campo>
      </div>
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Comprobante</th><th>Conexión</th><th>Titular</th><th>Anterior</th><th>Actual</th><th>Consumo</th><th>Tomada</th><th>Cobrador</th><th>Estado</th></tr></thead>
          <tbody>
            {datos?.results.map((l) => (
              <tr key={l.comprobante}>
                <td><Link className="font-semibold text-koape-rojo hover:underline" to={`/panel/lecturas/${l.comprobante}`}>{l.comprobante}</Link></td>
                <td>{l.conexion}</td>
                <td>{l.titular}</td>
                <td>{numero(l.lectura_anterior)}</td>
                <td className="font-semibold">{numero(l.lectura_actual)}</td>
                <td>{numero(l.consumo)}</td>
                <td className="whitespace-nowrap">{fechaHora(l.capturada_en)}</td>
                <td>{l.cobrador_nombre}</td>
                <td><InsigniaLectura l={l} />{l.motivo_revision && l.estado === 'requiere_revision' ? <div className="text-xs text-amber-700">{l.motivo_revision_nombre}</div> : null}</td>
              </tr>
            ))}
            {datos?.results.length === 0 && <tr><td colSpan={9} className="text-center text-koape-gris">Sin lecturas.</td></tr>}
          </tbody>
        </table>
      </div>
      {datos && <Paginador pagina={pagina} total={datos.count} alCambiar={setPagina} />}
    </div>
  )
}

type Accion = 'autorizar' | 'corregir' | 'anular' | null

export function FichaLectura() {
  const { comprobante = '' } = useParams()
  const { api, puede } = useSesion()
  const abrirPdf = useAbrirPdf()
  const [lectura, setLectura] = useState<Lectura | null>(null)
  const [error, setError] = useState('')
  const [exito, setExito] = useState('')
  const [accion, setAccion] = useState<Accion>(null)
  const [liquidaciones, setLiquidaciones] = useState<Liquidacion[]>([])
  const ruta = `lecturas/${encodeURIComponent(comprobante)}/`
  const veLiquidaciones = puede('liquidaciones.consultar') || puede('tarifas.gestionar')

  useEffect(() => {
    if (!veLiquidaciones || !lectura) return
    api.get<Pagina<Liquidacion>>('liquidaciones/', { params: { lectura: comprobante } })
      .then((r) => setLiquidaciones(r.data.results)).catch(() => setLiquidaciones([]))
  }, [api, comprobante, veLiquidaciones, lectura])

  const cargar = useCallback(() => {
    api.get<Lectura>(ruta).then((r) => setLectura(r.data)).catch((e) => setError(mensajeDeError(e)))
  }, [api, ruta])
  useEffect(cargar, [cargar])

  if (!lectura) return error ? <Aviso tipo="error">{error}</Aviso> : <p className="text-koape-gris">Cargando…</p>
  const revisa = puede('lecturas.revisar')
  const mapa = `https://www.openstreetmap.org/?mlat=${lectura.latitud}&mlon=${lectura.longitud}#map=18/${lectura.latitud}/${lectura.longitud}`

  return (
    <div className="max-w-5xl space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm"><Link className="text-koape-rojo hover:underline" to="/panel/lecturas">← Lecturas</Link></p>
          <h1 className="text-2xl font-extrabold">Lectura {lectura.comprobante}</h1>
          <p className="text-sm text-koape-gris">Período {lectura.periodo} · recorrido <Link className="hover:underline" to={`/panel/recorridos/${lectura.recorrido}`}>{lectura.recorrido}</Link></p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <InsigniaLectura l={lectura} />
          <button className="boton-secundario" onClick={() => void abrirPdf(`${ruta}ticket/`)}>Ticket</button>
          <button className="boton-secundario" onClick={() => void abrirPdf(`${ruta}comprobante/`)}>Comprobante con foto (PDF)</button>
          {revisa && lectura.estado === 'requiere_revision' && <button className="boton-primario" onClick={() => setAccion('autorizar')}>Autorizar</button>}
          {revisa && lectura.estado !== 'anulada' && <button className="boton-secundario" onClick={() => setAccion('corregir')}>Corregir</button>}
          {revisa && lectura.estado !== 'anulada' && <button className="boton-secundario" onClick={() => setAccion('anular')}>Anular</button>}
        </div>
      </div>
      <Aviso tipo="error">{error}</Aviso>
      <Aviso tipo="exito">{exito}</Aviso>
      {lectura.estado === 'requiere_revision' && (
        <Aviso tipo="error">Requiere revisión: {lectura.motivo_revision_nombre}. Mire la foto y autorice, corrija o anule la lectura.</Aviso>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="tarjeta p-5">
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div><dt className="etiqueta">Conexión</dt><dd><Link className="font-semibold text-koape-rojo hover:underline" to={`/panel/conexiones/${lectura.conexion}`}>{lectura.conexion}</Link></dd></div>
            <div><dt className="etiqueta">Titular</dt><dd>{lectura.titular}</dd></div>
            <div><dt className="etiqueta">Dirección</dt><dd>{lectura.direccion || '—'}</dd></div>
            <div><dt className="etiqueta">Medidor</dt><dd className="font-semibold">{lectura.medidor}{lectura.medidor_numero && <span className="ml-1 font-mono font-normal text-koape-gris">N.º {lectura.medidor_numero}</span>}</dd></div>
            <div><dt className="etiqueta">Lectura anterior</dt><dd>{numero(lectura.lectura_anterior)} <span className="text-xs text-koape-gris">({lectura.fecha_lectura_anterior}{lectura.origen_anterior === 'instalacion' ? ', inicial de la instalación' : ''})</span></dd></div>
            <div><dt className="etiqueta">Lectura actual</dt><dd className="text-xl font-extrabold">{numero(lectura.lectura_actual)}</dd></div>
            <div><dt className="etiqueta">Consumo</dt><dd className="text-xl font-extrabold">{lectura.consumo !== null ? numero(lectura.consumo) : <span className="text-base text-amber-700">pendiente</span>}</dd></div>
            <div><dt className="etiqueta">Tomada</dt><dd>{fechaHora(lectura.capturada_en)}<br /><span className="text-xs text-koape-gris">recibida {fechaHora(lectura.sincronizada_en)}</span></dd></div>
            <div><dt className="etiqueta">Cobrador</dt><dd>{lectura.cobrador_nombre}</dd></div>
            <div><dt className="etiqueta">Ubicación</dt><dd><a className="text-koape-rojo hover:underline" href={mapa} target="_blank" rel="noreferrer">Ver en el mapa</a>
              <br /><span className="text-xs text-koape-gris">{lectura.precision_metros !== null ? `precisión ±${lectura.precision_metros} m` : ''}{lectura.distancia_metros !== null ? ` · a ${lectura.distancia_metros} m de la conexión` : ''}</span></dd></div>
            {lectura.comentario && <div className="col-span-2"><dt className="etiqueta">Comentario del cobrador</dt><dd>{lectura.comentario}</dd></div>}
            {lectura.resolucion && <div className="col-span-2"><dt className="etiqueta">Última resolución</dt><dd>{lectura.resolucion} <span className="text-xs text-koape-gris">({lectura.resuelta_por}, {fechaHora(lectura.resuelta_en)})</span></dd></div>}
          </dl>
        </section>
        <section className="tarjeta space-y-3 p-5">
          {lectura.fotos.map((f) => (
            <div key={f.n}>
              <p className="mb-1 text-xs font-semibold text-koape-gris">{f.principal ? 'Foto del medidor' : `Foto adicional ${f.n}`}{f.origen === 'galeria' ? ' · de la galería' : ''}</p>
              <FotoPrivada ruta={`${ruta}fotos/${f.n}/`} alt={f.principal ? 'Medidor' : 'Foto adicional'} className="max-h-96 w-full rounded-lg object-contain bg-koape-fondo" />
            </div>
          ))}
        </section>
      </div>
      {veLiquidaciones && lectura.estado !== 'requiere_revision' && (
        <section className="tarjeta p-5 text-sm">
          <h2 className="mb-2 text-lg font-bold">Liquidación</h2>
          {liquidaciones.length === 0 ? <p className="text-koape-gris">{lectura.estado === 'confirmada' ? 'Sin liquidar (no había tarifa vigente). Vea Tarifas → Liquidaciones.' : 'Sin liquidación.'}</p> : (
            <ul className="space-y-1">
              {liquidaciones.map((q) => (
                <li key={q.numero}><Link className="font-semibold text-koape-rojo hover:underline" to={`/panel/liquidaciones/${q.numero}`}>{q.numero}</Link>
                  {' · '}{q.tarifa_nombre} · Gs. {Number(q.total).toLocaleString('es-PY')} · {q.estado_nombre}</li>
              ))}
            </ul>
          )}
        </section>
      )}
      {accion && <DialogoAccion accion={accion} lectura={lectura} ruta={ruta} alCerrar={() => setAccion(null)}
        alListo={(l, m) => { setLectura(l); setAccion(null); setExito(m); setError('') }} />}
    </div>
  )
}

function DialogoAccion({ accion, lectura, ruta, alCerrar, alListo }: { accion: Exclude<Accion, null>; lectura: Lectura; ruta: string; alCerrar: () => void; alListo: (l: Lectura, mensaje: string) => void }) {
  const { api } = useSesion()
  const diferencia = Number(lectura.lectura_actual) - Number(lectura.lectura_anterior)
  const [motivo, setMotivo] = useState('')
  const [valor, setValor] = useState(accion === 'corregir' ? lectura.lectura_actual : diferencia >= 0 ? String(diferencia) : '')
  const [error, setError] = useState('')
  const titulos = { autorizar: 'Autorizar lectura', corregir: 'Corregir lectura', anular: 'Anular lectura' }

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setError('')
    const cuerpo: Record<string, string> = { motivo }
    if (accion === 'corregir') cuerpo.lectura_actual = valor
    if (accion === 'autorizar' && valor !== '') cuerpo.consumo = valor
    try {
      const r = await api.post<Lectura>(`${ruta}${accion}/`, cuerpo)
      alListo(r.data, { autorizar: 'Lectura autorizada.', corregir: 'Lectura corregida.', anular: 'Lectura anulada.' }[accion])
    } catch (err) {
      setError(mensajeDeError(err))
    }
  }

  return (
    <Modal titulo={titulos[accion]} alCerrar={alCerrar}>
      <form className="space-y-4" onSubmit={enviar}>
        <Aviso tipo="error">{error}</Aviso>
        {accion === 'autorizar' && (
          <>
            {diferencia < 0 && <p className="text-sm">La lectura actual ({numero(lectura.lectura_actual)}) es menor que la anterior ({numero(lectura.lectura_anterior)}). Indique el consumo a registrar: si el contador volvió a cero, es lo que faltaba hasta la capacidad más la lectura actual.</p>}
            <Campo etiqueta="Consumo a registrar"><input className="campo" inputMode="decimal" value={valor} onChange={(e) => setValor(e.target.value)} /></Campo>
          </>
        )}
        {accion === 'corregir' && (
          <Campo etiqueta="Lectura correcta (la que se ve en la foto)"><input className="campo" inputMode="decimal" value={valor} onChange={(e) => setValor(e.target.value)} /></Campo>
        )}
        {accion === 'anular' && <p className="text-sm">La lectura queda anulada en el historial (no se borra) y la conexión vuelve a figurar sin lectura del período.</p>}
        <Campo etiqueta="Motivo (obligatorio, queda en la auditoría)"><textarea className="campo" value={motivo} onChange={(e) => setMotivo(e.target.value)} /></Campo>
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={!motivo.trim() || (accion === 'corregir' && !valor)}>Confirmar</button>
        </div>
      </form>
    </Modal>
  )
}

/** Historial de lecturas de una conexión (para su ficha). */
export function LecturasDeConexion({ conexion }: { conexion: string }) {
  const { api, puede } = useSesion()
  const [filas, setFilas] = useState<Lectura[] | null>(null)
  useEffect(() => {
    if (!puede('lecturas.consultar') && !puede('lecturas.revisar')) return
    api.get<Pagina<Lectura>>('lecturas/', { params: { conexion, tamanio: 24 } }).then((r) => setFilas(r.data.results)).catch(() => setFilas([]))
  }, [api, conexion, puede])
  if (!puede('lecturas.consultar') && !puede('lecturas.revisar')) return null
  return (
    <section className="tarjeta p-5">
      <h2 className="mb-4 text-lg font-bold">Lecturas</h2>
      {!filas ? <p className="text-sm text-koape-gris">Cargando…</p> : filas.length === 0 ? <p className="text-sm text-koape-gris">Todavía no tiene lecturas.</p> : (
        <div className="overflow-x-auto">
          <table className="tabla">
            <thead><tr><th>Período</th><th>Comprobante</th><th>Medidor</th><th>Anterior</th><th>Actual</th><th>Consumo</th><th>Estado</th></tr></thead>
            <tbody>
              {filas.map((l) => (
                <tr key={l.comprobante}>
                  <td>{l.periodo}</td>
                  <td><Link className="font-semibold text-koape-rojo hover:underline" to={`/panel/lecturas/${l.comprobante}`}>{l.comprobante}</Link></td>
                  <td>{l.medidor}{l.medidor_numero && <span className="block font-mono text-xs text-koape-gris">N.º {l.medidor_numero}</span>}</td>
                  <td>{numero(l.lectura_anterior)}</td>
                  <td>{numero(l.lectura_actual)}</td>
                  <td>{numero(l.consumo)}</td>
                  <td><InsigniaLectura l={l} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
