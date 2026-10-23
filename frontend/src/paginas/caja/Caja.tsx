import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { mensajeDeError } from '../../api/cliente'
import type { Caja, CategoriaGasto, FormaPago, Gasto, MiCaja, MovimientoCaja, Pagina, SesionCaja } from '../../api/tipos'
import { Aviso } from '../../componentes/Aviso'
import { Campo } from '../../componentes/Campo'
import { Encabezado } from '../../componentes/Encabezado'
import { Modal } from '../../componentes/Modal'
import { Paginador } from '../../componentes/Paginador'
import { useSesion } from '../../sesion/ContextoSesion'
import { fechaHora } from '../../utilidades/fechas'
import { guaranies } from '../cobranzas/Cobranzas'
import { useAbrirPdf } from '../lecturas/Lecturas'
import { gs } from '../tarifas/Tarifas'

const fecha = (v: string | null) => (v ? new Date(`${v}T12:00:00`).toLocaleDateString('es-PY') : '—')
const COLOR_SESION: Record<SesionCaja['estado'], string> = {
  abierta: 'bg-emerald-100 text-emerald-800', en_revision: 'bg-amber-100 text-amber-800', cerrada: 'bg-slate-200 text-slate-700',
}
const COLOR_GASTO: Record<Gasto['estado'], string> = {
  registrado: 'bg-sky-100 text-sky-800', confirmado: 'bg-emerald-100 text-emerald-800', anulado: 'bg-slate-200 text-slate-600',
}
const Insignia = ({ texto, color }: { texto: string; color: string }) => <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${color}`}>{texto}</span>

/** Aviso para las pantallas de cobro: sin caja abierta no se cobra. */
export function AvisoCajaCerrada() {
  const { api, puede } = useSesion()
  const [abierta, setAbierta] = useState<boolean | null>(null)
  useEffect(() => {
    if (!puede('caja.operar')) { setAbierta(false); return }
    api.get<MiCaja>('caja/mi-sesion/').then((r) => setAbierta(!!r.data.sesion)).catch(() => setAbierta(null))
  }, [api, puede])
  if (abierta !== false) return null
  return (
    <Aviso tipo="error">
      Para cobrar hace falta tener su caja abierta. {puede('caja.operar')
        ? <Link className="font-semibold underline" to="/panel/mi-caja">Abrir mi caja</Link>
        : 'Pida el permiso «Abrir y cerrar su propia caja» al administrador.'}
    </Aviso>
  )
}

function TablaResumen({ s }: { s: SesionCaja }) {
  const declarado = new Map(s.declaraciones.map((d) => [d.forma_pago, d]))
  const conCierre = s.declaraciones.length > 0
  return (
    <div className="overflow-x-auto">
      <table className="tabla">
        <thead><tr><th>Forma de pago</th><th className="text-right">Inicial</th><th className="text-right">Ingresos</th><th className="text-right">Egresos</th><th className="text-right">Esperado</th>
          {conCierre && <><th className="text-right">Contado</th><th className="text-right">Diferencia</th></>}</tr></thead>
        <tbody>
          {s.resumen.map((f) => {
            const d = declarado.get(f.forma_pago)
            return (
              <tr key={f.forma_pago}>
                <td className="font-semibold">{f.nombre}</td>
                <td className="text-right">{gs(f.saldo_inicial)}</td>
                <td className="text-right">{gs(f.ingresos)}</td>
                <td className="text-right">{gs(f.egresos)}</td>
                <td className="text-right font-bold">{gs(f.esperado)}</td>
                {conCierre && <><td className="text-right">{d ? gs(d.declarado) : '—'}</td>
                  <td className={`text-right font-bold ${d && Number(d.diferencia) !== 0 ? 'text-koape-rojo' : ''}`}>{d ? gs(d.diferencia) : '—'}</td></>}
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-koape-gris">Cada forma de pago se controla por separado: las transferencias y el POS no son dinero dentro de la caja.</p>
    </div>
  )
}

function Movimientos({ referencia, version }: { referencia: string; version: number }) {
  const { api } = useSesion()
  const [lista, setLista] = useState<MovimientoCaja[]>([])
  useEffect(() => {
    api.get<MovimientoCaja[]>(`sesiones-caja/${referencia}/movimientos/`).then((r) => setLista(r.data)).catch(() => setLista([]))
  }, [api, referencia, version])
  return (
    <div className="overflow-x-auto">
      <table className="tabla">
        <thead><tr><th>Hora</th><th>Origen</th><th>Detalle</th><th>Forma</th><th className="text-right">Importe</th></tr></thead>
        <tbody>
          {lista.map((m, n) => (
            <tr key={n} className={m.revertido ? 'text-koape-gris line-through' : ''}>
              <td>{fechaHora(m.fecha_hora)}</td>
              <td>{m.origen_nombre}</td>
              <td>
                {m.recibo ? <Link className="text-koape-rojo hover:underline" to={`/panel/recibos/${m.recibo}`}>{m.descripcion}</Link>
                  : m.gasto ? <Link className="text-koape-rojo hover:underline" to={`/panel/gastos/${m.gasto}`}>{m.descripcion}</Link> : m.descripcion}
              </td>
              <td>{m.forma_pago}</td>
              <td className={`text-right font-semibold ${m.tipo === 'egreso' ? 'text-koape-rojo' : 'text-emerald-700'}`}>{m.tipo === 'egreso' ? '− ' : '+ '}{gs(m.importe)}</td>
            </tr>
          ))}
          {lista.length === 0 && <tr><td colSpan={5} className="text-center text-koape-gris">Sin movimientos todavía.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

/** El cajero abre su caja, ve lo que entra y sale, y la cierra contando cada forma de pago. */
export function MiCajaPagina() {
  const { api } = useSesion()
  const navegar = useNavigate()
  const abrirPdf = useAbrirPdf()
  const [datos, setDatos] = useState<MiCaja | null>(null)
  const [caja, setCaja] = useState('')
  const [inicial, setInicial] = useState('')
  const [error, setError] = useState('')
  const [cerrando, setCerrando] = useState(false)
  const [contado, setContado] = useState<Record<string, string>>({})
  const [observaciones, setObservaciones] = useState('')
  const [procesando, setProcesando] = useState(false)
  const [version, setVersion] = useState(0)

  const cargar = useCallback(() => {
    api.get<MiCaja>('caja/mi-sesion/').then((r) => { setDatos(r.data); setCaja(r.data.cajas_libres[0]?.Code ?? '') })
      .catch((e) => setError(mensajeDeError(e)))
  }, [api])
  useEffect(cargar, [cargar])

  async function abrir(e: FormEvent) {
    e.preventDefault()
    if (procesando) return
    setProcesando(true)
    setError('')
    try {
      setDatos((await api.post<MiCaja>('caja/mi-sesion/', { caja, saldo_inicial: String(guaranies(inicial)) })).data)
    } catch (err) {
      setError(mensajeDeError(err))
    } finally {
      setProcesando(false)
    }
  }

  const s = datos?.sesion
  const diferencias = s ? s.resumen.filter((f) => contado[f.forma_pago] !== undefined && contado[f.forma_pago] !== '' && guaranies(contado[f.forma_pago]) !== Number(f.esperado)) : []
  const completo = !!s && s.resumen.every((f) => (contado[f.forma_pago] ?? '') !== '')

  async function cerrar(e: FormEvent) {
    e.preventDefault()
    if (!s || procesando) return
    setProcesando(true)
    setError('')
    try {
      const r = await api.post<SesionCaja>(`sesiones-caja/${s.referencia}/cerrar/`, {
        declarados: s.resumen.map((f) => ({ forma_pago: f.forma_pago, importe: String(guaranies(contado[f.forma_pago] ?? '')) })),
        observaciones,
      })
      navegar(`/panel/sesiones-caja/${r.data.referencia}`)
    } catch (err) {
      setError(mensajeDeError(err))
      cargar()
    } finally {
      setProcesando(false)
    }
  }

  return (
    <div className="max-w-4xl space-y-4">
      <Encabezado titulo="Mi caja" descripcion="Abra su caja al empezar el turno: todo lo que cobre o pague queda en ella. Al terminar, ciérrela contando cada forma de pago." />
      <Aviso tipo="error">{error}</Aviso>
      {datos && !s && (
        <form className="tarjeta space-y-4 p-5" onSubmit={(e) => void abrir(e)}>
          <h2 className="font-bold">Abrir caja</h2>
          {datos.cajas_libres.length === 0 ? <p className="text-sm text-koape-gris">No hay cajas libres: todas están abiertas por otro cajero o desactivadas.</p> : (
            <div className="grid gap-4 sm:grid-cols-2">
              <Campo etiqueta="Caja">
                <select className="campo" value={caja} onChange={(e) => setCaja(e.target.value)}>
                  {datos.cajas_libres.map((c) => <option key={c.Code} value={c.Code}>{c.Code} · {c.nombre}</option>)}
                </select>
              </Campo>
              <Campo etiqueta="Efectivo inicial (cambio) en Gs."><input className="campo" inputMode="numeric" placeholder="0" value={inicial} onChange={(e) => setInicial(e.target.value)} /></Campo>
            </div>
          )}
          <button className="boton-primario" disabled={!caja || procesando}>Abrir mi caja</button>
        </form>
      )}
      {s && (
        <>
          <section className="tarjeta space-y-3 p-5">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h2 className="text-lg font-bold">Caja {s.caja} · {s.caja_nombre}</h2>
                <p className="text-sm text-koape-gris">Abierta {fechaHora(s.abierta_en)} · sesión {s.referencia}</p>
              </div>
              <div className="flex gap-2">
                <button className="boton-secundario" onClick={() => void abrirPdf(`sesiones-caja/${s.referencia}/pdf/`)}>Arqueo (PDF)</button>
                <button className="boton-primario" onClick={() => setCerrando(true)}>Cerrar caja</button>
              </div>
            </div>
            <TablaResumen s={s} />
          </section>
          <section className="tarjeta p-5">
            <div className="mb-2 flex items-center justify-between"><h2 className="font-bold">Movimientos</h2>
              <button className="text-sm text-koape-rojo hover:underline" onClick={() => { cargar(); setVersion((n) => n + 1) }}>Actualizar</button></div>
            <Movimientos referencia={s.referencia} version={version} />
          </section>
          {cerrando && (
            <Modal titulo="Cerrar caja" alCerrar={() => setCerrando(false)}>
              <form className="space-y-4" onSubmit={(e) => void cerrar(e)}>
                <p className="text-sm">Cuente lo que tiene en cada forma de pago y escríbalo. Si algo no coincide con lo esperado, la caja queda <b>en revisión</b> para el supervisor.</p>
                {s.resumen.map((f) => (
                  <Campo key={f.forma_pago} etiqueta={`${f.nombre} (esperado ${gs(f.esperado)})`}>
                    <input className="campo" inputMode="numeric" value={contado[f.forma_pago] ?? ''} onChange={(e) => setContado({ ...contado, [f.forma_pago]: e.target.value })} />
                  </Campo>
                ))}
                {diferencias.length > 0 && <Aviso tipo="error">Hay diferencias en: {diferencias.map((f) => `${f.nombre} (${gs(guaranies(contado[f.forma_pago]) - Number(f.esperado))})`).join(', ')}. Explíquelas abajo.</Aviso>}
                <Campo etiqueta={diferencias.length ? 'Observaciones (obligatorio)' : 'Observaciones'}><textarea className="campo" value={observaciones} onChange={(e) => setObservaciones(e.target.value)} /></Campo>
                <div className="flex justify-end gap-2">
                  <button type="button" className="boton-secundario" onClick={() => setCerrando(false)}>Cancelar</button>
                  <button className="boton-primario" disabled={!completo || procesando || (diferencias.length > 0 && !observaciones.trim())}>Cerrar caja</button>
                </div>
              </form>
            </Modal>
          )}
        </>
      )}
    </div>
  )
}

export function SesionesCaja() {
  const { api } = useSesion()
  const [filtros, setFiltros] = useState({ estado: '', caja: '', desde: '', hasta: '' })
  const [pagina, setPagina] = useState(1)
  const [datos, setDatos] = useState<Pagina<SesionCaja> | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const params = Object.fromEntries(Object.entries({ ...filtros, pagina }).filter(([, v]) => v !== ''))
    api.get<Pagina<SesionCaja>>('sesiones-caja/', { params }).then((r) => { setDatos(r.data); setError('') }).catch((e) => setError(mensajeDeError(e)))
  }, [api, filtros, pagina])
  const filtrar = (c: Partial<typeof filtros>) => { setPagina(1); setFiltros({ ...filtros, ...c }) }
  return (
    <div>
      <Encabezado titulo="Sesiones de caja" descripcion="Aperturas y cierres de caja. Las que cerraron con diferencias quedan en revisión." />
      <Aviso tipo="error">{error}</Aviso>
      <div className="mb-4 grid gap-3 sm:grid-cols-4">
        <Campo etiqueta="Estado">
          <select className="campo" value={filtros.estado} onChange={(e) => filtrar({ estado: e.target.value })}>
            <option value="">Todas</option><option value="abierta">Abiertas</option><option value="en_revision">En revisión</option><option value="cerrada">Cerradas</option>
          </select>
        </Campo>
        <Campo etiqueta="Caja"><input className="campo" value={filtros.caja} onChange={(e) => filtrar({ caja: e.target.value })} /></Campo>
        <Campo etiqueta="Desde"><input type="date" className="campo" value={filtros.desde} onChange={(e) => filtrar({ desde: e.target.value })} /></Campo>
        <Campo etiqueta="Hasta"><input type="date" className="campo" value={filtros.hasta} onChange={(e) => filtrar({ hasta: e.target.value })} /></Campo>
      </div>
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Sesión</th><th>Caja</th><th>Cajero</th><th>Apertura</th><th>Cierre</th><th className="text-right">Diferencia</th><th>Estado</th></tr></thead>
          <tbody>
            {datos?.results.map((s) => {
              // Por forma de pago: un faltante en efectivo y un sobrante en transferencias no se compensan.
              const conDiferencia = s.declaraciones.filter((d) => Number(d.diferencia) !== 0)
              return (
                <tr key={s.referencia}>
                  <td><Link className="font-semibold text-koape-rojo hover:underline" to={`/panel/sesiones-caja/${s.referencia}`}>{s.referencia}</Link></td>
                  <td>{s.caja}</td><td>{s.responsable}</td><td>{fechaHora(s.abierta_en)}</td><td>{s.cerrada_en ? fechaHora(s.cerrada_en) : '—'}</td>
                  <td className={`text-right ${conDiferencia.length ? 'font-bold text-koape-rojo' : ''}`}>
                    {!s.declaraciones.length ? '—' : conDiferencia.length ? conDiferencia.map((d) => `${d.nombre} ${gs(d.diferencia)}`).join(' · ') : 'Sin diferencia'}
                  </td>
                  <td><Insignia texto={s.estado_nombre} color={COLOR_SESION[s.estado]} /></td>
                </tr>
              )
            })}
            {datos?.results.length === 0 && <tr><td colSpan={7} className="text-center text-koape-gris">Sin sesiones.</td></tr>}
          </tbody>
        </table>
      </div>
      {datos && <Paginador pagina={pagina} total={datos.count} alCambiar={setPagina} />}
    </div>
  )
}

export function FichaSesion() {
  const { referencia = '' } = useParams()
  const { api, puede } = useSesion()
  const abrirPdf = useAbrirPdf()
  const [s, setS] = useState<SesionCaja | null>(null)
  const [error, setError] = useState('')
  const [comentario, setComentario] = useState('')
  const ruta = `sesiones-caja/${encodeURIComponent(referencia)}/`
  useEffect(() => { api.get<SesionCaja>(ruta).then((r) => setS(r.data)).catch((e) => setError(mensajeDeError(e))) }, [api, ruta])

  async function revisar(e: FormEvent) {
    e.preventDefault()
    setError('')
    try { setS((await api.post<SesionCaja>(`${ruta}revisar/`, { comentario })).data) } catch (err) { setError(mensajeDeError(err)) }
  }

  if (!s) return error ? <Aviso tipo="error">{error}</Aviso> : <p className="text-koape-gris">Cargando…</p>
  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm"><Link className="text-koape-rojo hover:underline" to="/panel/sesiones-caja">← Sesiones de caja</Link></p>
          <h1 className="text-2xl font-extrabold">Caja {s.caja} · sesión {s.referencia}</h1>
          <p className="text-sm text-koape-gris">{s.responsable} · abierta {fechaHora(s.abierta_en)}{s.cerrada_en ? ` · cerrada ${fechaHora(s.cerrada_en)}` : ''}</p>
        </div>
        <div className="flex items-center gap-2"><Insignia texto={s.estado_nombre} color={COLOR_SESION[s.estado]} />
          <button className="boton-secundario" onClick={() => void abrirPdf(`${ruta}pdf/`)}>Arqueo (PDF)</button></div>
      </div>
      <Aviso tipo="error">{error}</Aviso>
      <section className="tarjeta p-5"><TablaResumen s={s} />
        {s.observaciones_cierre && <p className="mt-3 text-sm"><b>Observaciones del cierre:</b> {s.observaciones_cierre}</p>}
        {s.comentario_revision && <p className="mt-1 text-sm"><b>Revisión</b>{s.revisada_por ? ` (${s.revisada_por}, ${fechaHora(s.revisada_en)})` : ''}: {s.comentario_revision}</p>}
      </section>
      {s.estado === 'en_revision' && puede('caja.supervisar') && (
        <form className="tarjeta space-y-3 p-5" onSubmit={(e) => void revisar(e)}>
          <h2 className="font-bold">Revisar diferencias</h2>
          <Campo etiqueta="Resultado de la revisión (qué se hizo con la diferencia)"><textarea className="campo" value={comentario} onChange={(e) => setComentario(e.target.value)} /></Campo>
          <button className="boton-primario" disabled={!comentario.trim()}>Dar por revisada</button>
        </form>
      )}
      <section className="tarjeta p-5"><h2 className="mb-2 font-bold">Movimientos</h2><Movimientos referencia={s.referencia} version={0} /></section>
    </div>
  )
}

/** Mantenimiento simple de un maestro con Code (cajas, categorías de gasto). */
function Maestro<T extends { Code: string; nombre: string; activa: boolean }>({ titulo, descripcion, ruta, permiso, columnas }:
  { titulo: string; descripcion: string; ruta: string; permiso: string; columnas?: (x: T) => ReactNode }) {
  const { api, puede } = useSesion()
  const [lista, setLista] = useState<T[]>([])
  const [error, setError] = useState('')
  const [edicion, setEdicion] = useState<T | 'nuevo' | null>(null)
  const [form, setForm] = useState({ Code: '', nombre: '', activa: true })
  const gestiona = puede(permiso)
  const cargar = useCallback(() => { api.get<T[]>(ruta).then((r) => setLista(r.data)).catch((e) => setError(mensajeDeError(e))) }, [api, ruta])
  useEffect(cargar, [cargar])
  const editar = (x: T | 'nuevo') => { setEdicion(x); setForm(x === 'nuevo' ? { Code: '', nombre: '', activa: true } : { Code: x.Code, nombre: x.nombre, activa: x.activa }) }

  async function guardar(e: FormEvent) {
    e.preventDefault()
    setError('')
    try {
      if (edicion === 'nuevo') await api.post(ruta, form)
      else if (edicion) await api.patch(`${ruta}${encodeURIComponent(edicion.Code)}/`, { nombre: form.nombre, activa: form.activa })
      setEdicion(null)
      cargar()
    } catch (err) { setError(mensajeDeError(err)) }
  }

  return (
    <div className="max-w-3xl">
      <Encabezado titulo={titulo} descripcion={descripcion} acciones={gestiona && <button className="boton-primario" onClick={() => editar('nuevo')}>Agregar</button>} />
      <Aviso tipo="error">{error}</Aviso>
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Código</th><th>Nombre</th>{columnas && <th>Estado actual</th>}<th>Activa</th><th /></tr></thead>
          <tbody>{lista.map((x) => (
            <tr key={x.Code} className={x.activa ? '' : 'text-koape-gris'}>
              <td className="font-semibold">{x.Code}</td><td>{x.nombre}</td>{columnas && <td>{columnas(x)}</td>}<td>{x.activa ? 'Sí' : 'No'}</td>
              <td>{gestiona && <button className="text-sm text-koape-rojo hover:underline" onClick={() => editar(x)}>Editar</button>}</td>
            </tr>))}</tbody>
        </table>
      </div>
      {edicion && (
        <Modal titulo={edicion === 'nuevo' ? 'Agregar' : `Editar ${edicion.Code}`} alCerrar={() => setEdicion(null)}>
          <form className="space-y-4" onSubmit={(e) => void guardar(e)}>
            {edicion === 'nuevo' && <Campo etiqueta="Código (no se cambia después)"><input className="campo" value={form.Code} onChange={(e) => setForm({ ...form, Code: e.target.value })} /></Campo>}
            <Campo etiqueta="Nombre"><input className="campo" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} /></Campo>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.activa} onChange={(e) => setForm({ ...form, activa: e.target.checked })} /> Activa</label>
            <div className="flex justify-end gap-2"><button type="button" className="boton-secundario" onClick={() => setEdicion(null)}>Cancelar</button>
              <button className="boton-primario" disabled={!form.nombre.trim() || (edicion === 'nuevo' && !form.Code.trim())}>Guardar</button></div>
          </form>
        </Modal>
      )}
    </div>
  )
}

export const Cajas = () => <Maestro<Caja> titulo="Cajas" descripcion="Ventanillas o puntos de cobro. Cada cajero abre su sesión en una caja libre." ruta="cajas/" permiso="caja.supervisar"
  columnas={(c) => (c.abierta_por ? `Abierta por ${c.abierta_por}` : 'Libre')} />
export const CategoriasGasto = () => <Maestro<CategoriaGasto> titulo="Categorías de gastos" descripcion="Para agrupar los gastos en los informes." ruta="categorias-gasto/" permiso="gastos.confirmar" />

export function Gastos() {
  const { api, puede } = useSesion()
  const navegar = useNavigate()
  const [filtros, setFiltros] = useState({ buscar: '', estado: '', categoria: '', desde: '', hasta: '' })
  const [pagina, setPagina] = useState(1)
  const [datos, setDatos] = useState<Pagina<Gasto> | null>(null)
  const [categorias, setCategorias] = useState<CategoriaGasto[]>([])
  const [nuevo, setNuevo] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => { api.get<CategoriaGasto[]>('categorias-gasto/').then((r) => setCategorias(r.data)).catch(() => setCategorias([])) }, [api])
  useEffect(() => {
    const t = setTimeout(() => {
      const params = Object.fromEntries(Object.entries({ ...filtros, pagina }).filter(([, v]) => v !== ''))
      api.get<Pagina<Gasto>>('gastos/', { params }).then((r) => { setDatos(r.data); setError('') }).catch((e) => setError(mensajeDeError(e)))
    }, 250)
    return () => clearTimeout(t)
  }, [api, filtros, pagina])
  const filtrar = (c: Partial<typeof filtros>) => { setPagina(1); setFiltros({ ...filtros, ...c }) }
  return (
    <div>
      <Encabezado titulo="Gastos" descripcion="Gastos referenciales (no es contabilidad). Un gasto sale de la caja recién cuando se confirma."
        acciones={puede('gastos.registrar') && <button className="boton-primario" onClick={() => setNuevo(true)}>Registrar gasto</button>} />
      <Aviso tipo="error">{error}</Aviso>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Campo etiqueta="Buscar"><input className="campo" placeholder="Motivo, beneficiario, comprobante" value={filtros.buscar} onChange={(e) => filtrar({ buscar: e.target.value })} /></Campo>
        <Campo etiqueta="Estado">
          <select className="campo" value={filtros.estado} onChange={(e) => filtrar({ estado: e.target.value })}>
            <option value="">Todos</option><option value="registrado">Sin confirmar</option><option value="confirmado">Confirmados</option><option value="anulado">Anulados</option>
          </select>
        </Campo>
        <Campo etiqueta="Categoría">
          <select className="campo" value={filtros.categoria} onChange={(e) => filtrar({ categoria: e.target.value })}>
            <option value="">Todas</option>{categorias.map((c) => <option key={c.Code} value={c.Code}>{c.nombre}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Desde"><input type="date" className="campo" value={filtros.desde} onChange={(e) => filtrar({ desde: e.target.value })} /></Campo>
        <Campo etiqueta="Hasta"><input type="date" className="campo" value={filtros.hasta} onChange={(e) => filtrar({ hasta: e.target.value })} /></Campo>
      </div>
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Fecha</th><th>Motivo</th><th>Categoría</th><th>Beneficiario</th><th>Comprobante</th><th className="text-right">Importe</th><th>Estado</th></tr></thead>
          <tbody>
            {datos?.results.map((g) => (
              <tr key={g.referencia} className={g.estado === 'anulado' ? 'text-koape-gris' : ''}>
                <td>{fecha(g.fecha)}</td>
                <td><Link className="font-semibold text-koape-rojo hover:underline" to={`/panel/gastos/${g.referencia}`}>{g.motivo}</Link></td>
                <td>{g.categoria_nombre}</td><td>{g.beneficiario}</td>
                <td className="text-xs">{g.numero_comprobante || (g.boleta ? `Boleta ${g.boleta.numero}` : '—')}{g.adjuntos.length ? ' 📎' : ''}</td>
                <td className="text-right font-semibold">{gs(g.importe)}</td>
                <td><Insignia texto={g.estado_nombre} color={COLOR_GASTO[g.estado]} /></td>
              </tr>
            ))}
            {datos?.results.length === 0 && <tr><td colSpan={7} className="text-center text-koape-gris">Sin gastos.</td></tr>}
          </tbody>
        </table>
      </div>
      {datos && <Paginador pagina={pagina} total={datos.count} alCambiar={setPagina} />}
      {nuevo && <EditarGasto gasto={null} alCerrar={() => setNuevo(false)} alGuardar={(g) => navegar(`/panel/gastos/${g.referencia}`)} />}
    </div>
  )
}

function EditarGasto({ gasto, alCerrar, alGuardar }: { gasto: Gasto | null; alCerrar: () => void; alGuardar: (g: Gasto) => void }) {
  const { api } = useSesion()
  const [categorias, setCategorias] = useState<CategoriaGasto[]>([])
  const [formas, setFormas] = useState<FormaPago[]>([])
  const [form, setForm] = useState({
    fecha: gasto?.fecha ?? new Date().toLocaleDateString('en-CA'), motivo: gasto?.motivo ?? '', importe: gasto ? Number(gasto.importe).toLocaleString('es-PY') : '',
    categoria: gasto?.categoria ?? '', forma_pago: gasto?.forma_pago ?? 'EFECTIVO', numero_comprobante: gasto?.numero_comprobante ?? '',
    beneficiario: gasto?.beneficiario ?? '', responsable: gasto?.responsable ?? '', observaciones: gasto?.observaciones ?? '',
  })
  const [error, setError] = useState('')
  const [guardando, setGuardando] = useState(false)
  useEffect(() => {
    api.get<CategoriaGasto[]>('categorias-gasto/', { params: { activas: 1 } }).then((r) => { setCategorias(r.data); setForm((f) => ({ ...f, categoria: f.categoria || r.data[0]?.Code || '' })) }).catch(() => setCategorias([]))
    api.get<FormaPago[]>('formas-pago/', { params: { activas: 1 } }).then((r) => setFormas(r.data)).catch(() => setFormas([]))
  }, [api])
  const campo = (k: keyof typeof form, etiqueta: string, tipo = 'text') => (
    <Campo etiqueta={etiqueta}><input type={tipo} className="campo" value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></Campo>
  )

  async function guardar(e: FormEvent) {
    e.preventDefault()
    if (guardando) return
    setGuardando(true)
    setError('')
    try {
      const cuerpo = { ...form, importe: String(guaranies(form.importe)) }
      const r = gasto ? await api.patch<Gasto>(`gastos/${gasto.referencia}/`, cuerpo) : await api.post<Gasto>('gastos/', cuerpo)
      alGuardar(r.data)
    } catch (err) { setError(mensajeDeError(err)) } finally { setGuardando(false) }
  }

  return (
    <Modal titulo={gasto ? `Corregir gasto ${gasto.referencia}` : 'Registrar gasto'} alCerrar={alCerrar}>
      <form className="space-y-3" onSubmit={(e) => void guardar(e)}>
        <Aviso tipo="error">{error}</Aviso>
        <div className="grid gap-3 sm:grid-cols-2">
          {campo('fecha', 'Fecha', 'date')}
          <Campo etiqueta="Importe (Gs.)"><input className="campo" inputMode="numeric" value={form.importe} onChange={(e) => setForm({ ...form, importe: e.target.value })} /></Campo>
        </div>
        {campo('motivo', 'Motivo')}
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo etiqueta="Categoría"><select className="campo" value={form.categoria} onChange={(e) => setForm({ ...form, categoria: e.target.value })}>{categorias.map((c) => <option key={c.Code} value={c.Code}>{c.nombre}</option>)}</select></Campo>
          <Campo etiqueta="Forma de pago"><select className="campo" value={form.forma_pago} onChange={(e) => setForm({ ...form, forma_pago: e.target.value })}>{formas.map((f) => <option key={f.Code} value={f.Code}>{f.nombre}</option>)}</select></Campo>
          {campo('beneficiario', 'Beneficiario (a quién se pagó)')}
          {campo('responsable', 'Responsable')}
        </div>
        {campo('numero_comprobante', 'N° de comprobante (si tiene; si no, imprima la boleta interna)')}
        <Campo etiqueta="Observaciones"><textarea className="campo" value={form.observaciones} onChange={(e) => setForm({ ...form, observaciones: e.target.value })} /></Campo>
        <div className="flex justify-end gap-2"><button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={guardando || !form.categoria || !form.forma_pago || !form.motivo.trim() || !form.beneficiario.trim() || guaranies(form.importe) <= 0}>Guardar</button></div>
      </form>
    </Modal>
  )
}

export function FichaGasto() {
  const { referencia = '' } = useParams()
  const { api, puede } = useSesion()
  const abrirPdf = useAbrirPdf()
  const [g, setG] = useState<Gasto | null>(null)
  const [error, setError] = useState('')
  const [exito, setExito] = useState('')
  const [editando, setEditando] = useState(false)
  const [anulando, setAnulando] = useState(false)
  const [motivo, setMotivo] = useState('')
  const [procesando, setProcesando] = useState(false)
  const ruta = `gastos/${encodeURIComponent(referencia)}/`
  const cargar = useCallback(() => { api.get<Gasto>(ruta).then((r) => setG(r.data)).catch((e) => setError(mensajeDeError(e))) }, [api, ruta])
  useEffect(cargar, [cargar])

  async function accion(sub: string, cuerpo: object | FormData, mensaje: string) {
    if (procesando) return
    setProcesando(true)
    setError('')
    setExito('')
    try {
      setG((await api.post<Gasto>(`${ruta}${sub}/`, cuerpo)).data)
      setExito(mensaje)
      setAnulando(false)
    } catch (err) { setError(mensajeDeError(err)) } finally { setProcesando(false) }
  }
  function subir(tipo: string, entrada: HTMLInputElement) {
    const archivo = entrada.files?.[0]
    entrada.value = '' // permite volver a elegir el mismo archivo
    if (!archivo) return
    if (procesando) { setError('Espere a que termine la operación anterior y vuelva a elegir el archivo.'); return }
    const datos = new FormData()
    datos.append('archivo', archivo)
    datos.append('tipo', tipo)
    void accion('adjuntos', datos, 'Archivo adjuntado.')
  }

  if (!g) return error ? <Aviso tipo="error">{error}</Aviso> : <p className="text-koape-gris">Cargando…</p>
  const vivo = g.estado !== 'anulado'
  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm"><Link className="text-koape-rojo hover:underline" to="/panel/gastos">← Gastos</Link></p>
          <h1 className="text-2xl font-extrabold">{g.motivo}</h1>
          <p className="text-sm text-koape-gris">{g.referencia} · registrado por {g.registrado_por} {fechaHora(g.creado_en)}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Insignia texto={g.estado_nombre} color={COLOR_GASTO[g.estado]} />
          {g.estado === 'registrado' && puede('gastos.registrar') && <button className="boton-secundario" onClick={() => setEditando(true)}>Corregir</button>}
          {g.estado === 'registrado' && puede('gastos.confirmar') && <button className="boton-primario" disabled={procesando} onClick={() => void accion('confirmar', {}, 'Gasto confirmado: salió de su caja.')}>Confirmar (sale de mi caja)</button>}
          {vivo && puede('gastos.confirmar') && <button className="boton-secundario" onClick={() => setAnulando(true)}>Anular</button>}
        </div>
      </div>
      <Aviso tipo="error">{error}</Aviso>
      <Aviso tipo="exito">{exito}</Aviso>
      {g.estado === 'anulado' && <Aviso tipo="error">Anulado {fechaHora(g.anulado_en)} por {g.anulado_por}: {g.motivo_anulacion}</Aviso>}
      <section className="tarjeta p-5">
        <dl className="grid gap-3 text-sm sm:grid-cols-3">
          <div><dt className="etiqueta">Importe</dt><dd className="text-xl font-extrabold">{gs(g.importe)}</dd></div>
          <div><dt className="etiqueta">Fecha</dt><dd>{fecha(g.fecha)}</dd></div>
          <div><dt className="etiqueta">Categoría</dt><dd>{g.categoria_nombre}</dd></div>
          <div><dt className="etiqueta">Beneficiario</dt><dd>{g.beneficiario}</dd></div>
          <div><dt className="etiqueta">Responsable</dt><dd>{g.responsable || '—'}</dd></div>
          <div><dt className="etiqueta">Forma de pago</dt><dd>{g.forma_pago_nombre}</dd></div>
          <div><dt className="etiqueta">Comprobante</dt><dd>{g.numero_comprobante || '—'}</dd></div>
          <div><dt className="etiqueta">Caja</dt><dd>{g.sesion ? <Link className="text-koape-rojo hover:underline" to={`/panel/sesiones-caja/${g.sesion}`}>{g.sesion}</Link> : 'sin confirmar'}{g.confirmado_por ? ` · ${g.confirmado_por}` : ''}</dd></div>
        </dl>
        {g.observaciones && <p className="mt-3 text-sm">{g.observaciones}</p>}
      </section>
      <section className="tarjeta space-y-3 p-5 text-sm">
        <h2 className="font-bold">Comprobantes</h2>
        <ul className="space-y-1">
          {g.adjuntos.map((a) => (
            <li key={a.codigo}><button className="text-koape-rojo hover:underline" onClick={() => void abrirPdf(`${ruta}adjuntos/${a.codigo}/`)}>{a.tipo_nombre} ({a.es_pdf ? 'PDF' : 'foto'})</button> · {a.subido_por} · {fechaHora(a.creado_en)}</li>
          ))}
          {g.adjuntos.length === 0 && <li className="text-koape-gris">Sin archivos adjuntos.</li>}
        </ul>
        {vivo && puede('gastos.registrar') && (
          <div className="flex flex-wrap gap-3">
            <label className="boton-secundario cursor-pointer">Adjuntar comprobante (foto o PDF)<input type="file" accept="image/*,application/pdf" className="hidden" onChange={(e) => subir('comprobante', e.target)} /></label>
            {!g.boleta && <button className="boton-secundario" disabled={procesando} onClick={() => void accion('boleta', {}, 'Boleta interna generada.')}>Generar boleta interna (sin comprobante)</button>}
          </div>
        )}
        {g.boleta && (
          <div className="rounded-lg border border-koape-gris-claro p-3">
            <p>Boleta interna <b>N° {g.boleta.numero}</b>: imprímala, hágala firmar y suba la foto firmada.</p>
            <div className="mt-2 flex flex-wrap gap-3">
              <button className="boton-secundario" onClick={() => void abrirPdf(`${ruta}boleta/pdf/`)}>Imprimir boleta (PDF)</button>
              {vivo && puede('gastos.registrar') && <label className="boton-secundario cursor-pointer">Subir boleta firmada<input type="file" accept="image/*,application/pdf" className="hidden" onChange={(e) => subir('boleta_firmada', e.target)} /></label>}
            </div>
            <p className="mt-2 text-xs text-koape-gris">La boleta interna es evidencia administrativa: no sustituye a un comprobante fiscal.</p>
          </div>
        )}
      </section>
      {editando && <EditarGasto gasto={g} alCerrar={() => setEditando(false)} alGuardar={(x) => { setG(x); setEditando(false); setExito('Gasto corregido.') }} />}
      {anulando && (
        <Modal titulo="Anular gasto" alCerrar={() => setAnulando(false)}>
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); void accion('anular', { motivo }, 'Gasto anulado.') }}>
            <p className="text-sm">{g.estado === 'confirmado' ? 'El egreso no se borra: se registra un ingreso que lo compensa en la caja abierta (la suya si la original ya cerró).' : 'El gasto queda anulado en el historial.'}</p>
            <Campo etiqueta="Motivo (obligatorio)"><textarea className="campo" value={motivo} onChange={(e) => setMotivo(e.target.value)} /></Campo>
            <div className="flex justify-end gap-2"><button type="button" className="boton-secundario" onClick={() => setAnulando(false)}>Cancelar</button>
              <button className="boton-primario" disabled={!motivo.trim() || procesando}>Anular</button></div>
          </form>
        </Modal>
      )}
    </div>
  )
}
