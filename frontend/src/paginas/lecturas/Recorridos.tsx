import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { mensajeDeError } from '../../api/cliente'
import type { Avance, EstadoRecorrido, Pagina, ParadaRecorrido, Recorrido } from '../../api/tipos'
import { Aviso } from '../../componentes/Aviso'
import { Campo } from '../../componentes/Campo'
import { Encabezado } from '../../componentes/Encabezado'
import { Modal } from '../../componentes/Modal'
import { useSesion } from '../../sesion/ContextoSesion'
import { fechaHora } from '../../utilidades/fechas'
import { useTerritorio } from '../padron/Conexiones'

export const periodoActual = () => new Date().toLocaleDateString('en-CA').slice(0, 7)

const COLOR: Record<EstadoRecorrido, string> = {
  planificado: 'bg-slate-100 text-slate-700', abierto: 'bg-emerald-100 text-emerald-800',
  cerrado: 'bg-sky-100 text-sky-800', anulado: 'bg-rose-100 text-rose-700',
}

export function InsigniaRecorrido({ r }: { r: Pick<Recorrido, 'estado' | 'estado_nombre'> }) {
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${COLOR[r.estado]}`}>{r.estado_nombre.split(' (')[0]}</span>
}

export function BarraAvance({ a }: { a: Avance }) {
  const pct = (n: number) => (a.total ? (n / a.total) * 100 : 0)
  return (
    <div>
      <div className="flex h-2 overflow-hidden rounded-full bg-koape-fondo">
        <div className="bg-emerald-500" style={{ width: `${pct(a.confirmadas)}%` }} />
        <div className="bg-amber-400" style={{ width: `${pct(a.en_revision)}%` }} />
      </div>
      <p className="mt-1 text-xs text-koape-gris">
        {a.leidas} de {a.total} leídas{a.en_revision ? ` · ${a.en_revision} en revisión` : ''} · {a.pendientes} pendientes
      </p>
    </div>
  )
}

export function Recorridos() {
  const { api, puede } = useSesion()
  const navegar = useNavigate()
  const [periodo, setPeriodo] = useState(periodoActual())
  const [lista, setLista] = useState<Recorrido[]>([])
  const [error, setError] = useState('')
  const [nuevo, setNuevo] = useState(false)

  useEffect(() => {
    api.get<Pagina<Recorrido>>('recorridos/', { params: { periodo: periodo || undefined, tamanio: 100 } })
      .then((r) => { setLista(r.data.results); setError('') }).catch((e) => setError(mensajeDeError(e)))
  }, [api, periodo])

  return (
    <div>
      <Encabezado titulo="Recorridos" descripcion="Qué conexiones lee cada cobrador en el mes, y en qué orden."
        acciones={puede('recorridos.gestionar') && <button className="boton-primario" onClick={() => setNuevo(true)}>Nuevo recorrido</button>} />
      <Aviso tipo="error">{error}</Aviso>
      <div className="mb-4 flex items-end gap-3">
        <Campo etiqueta="Período"><input type="month" className="campo" value={periodo} onChange={(e) => setPeriodo(e.target.value)} /></Campo>
        <button className="boton-secundario" onClick={() => setPeriodo('')}>Todos</button>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {lista.map((r) => (
          <Link key={r.Code} to={`/panel/recorridos/${r.Code}`} className="tarjeta block p-5 hover:shadow-md">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-titulo text-lg font-bold">{r.nombre}</p>
                <p className="text-xs text-koape-gris">{r.Code} · {r.periodo}</p>
              </div>
              <InsigniaRecorrido r={r} />
            </div>
            <div className="mt-3"><BarraAvance a={r.avance} /></div>
            <p className="mt-2 text-xs text-koape-gris">
              {r.cobradores.filter((c) => c.activa).map((c) => c.nombre).join(', ') || 'Sin cobrador asignado'}
            </p>
          </Link>
        ))}
        {lista.length === 0 && <p className="text-sm text-koape-gris">No hay recorridos en ese período.</p>}
      </div>
      {nuevo && <FormularioRecorrido alCerrar={() => setNuevo(false)} alGuardar={(r) => navegar(`/panel/recorridos/${r.Code}`)} />}
    </div>
  )
}

function FormularioRecorrido({ recorrido, alCerrar, alGuardar }: { recorrido?: Recorrido; alCerrar: () => void; alGuardar: (r: Recorrido) => void }) {
  const { api } = useSesion()
  const [form, setForm] = useState({
    Code: recorrido?.Code ?? '', nombre: recorrido?.nombre ?? '', periodo: recorrido?.periodo ?? periodoActual(),
    fecha_desde: recorrido?.fecha_desde ?? '', fecha_hasta: recorrido?.fecha_hasta ?? '', observaciones: recorrido?.observaciones ?? '',
  })
  const [error, setError] = useState('')

  async function guardar(e: FormEvent) {
    e.preventDefault()
    setError('')
    const cuerpo = { ...form, fecha_desde: form.fecha_desde || null, fecha_hasta: form.fecha_hasta || null }
    try {
      const r = recorrido ? await api.patch<Recorrido>(`recorridos/${recorrido.Code}/`, cuerpo) : await api.post<Recorrido>('recorridos/', cuerpo)
      alGuardar(r.data)
    } catch (err) {
      setError(mensajeDeError(err))
    }
  }

  return (
    <Modal titulo={recorrido ? `Recorrido ${recorrido.Code}` : 'Nuevo recorrido'} alCerrar={alCerrar}>
      <form onSubmit={guardar} className="space-y-4">
        <Aviso tipo="error">{error}</Aviso>
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo etiqueta="Código"><input className="campo uppercase" required maxLength={40} disabled={!!recorrido} value={form.Code} onChange={(e) => setForm({ ...form, Code: e.target.value })} placeholder="Ej. CENTRO-2026-10" /></Campo>
          <Campo etiqueta="Período"><input type="month" className="campo" required disabled={!!recorrido} value={form.periodo} onChange={(e) => setForm({ ...form, periodo: e.target.value })} /></Campo>
          <Campo etiqueta="Nombre" ancho><input className="campo" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} placeholder="Ej. Centro, primera quincena" /></Campo>
          <Campo etiqueta="Desde"><input type="date" className="campo" value={form.fecha_desde} onChange={(e) => setForm({ ...form, fecha_desde: e.target.value })} /></Campo>
          <Campo etiqueta="Hasta"><input type="date" className="campo" value={form.fecha_hasta} onChange={(e) => setForm({ ...form, fecha_hasta: e.target.value })} /></Campo>
          <Campo etiqueta="Observaciones" ancho><textarea className="campo" value={form.observaciones} onChange={(e) => setForm({ ...form, observaciones: e.target.value })} /></Campo>
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={!form.Code.trim() || !form.nombre.trim() || !form.periodo}>Guardar</button>
        </div>
      </form>
    </Modal>
  )
}

type Dialogo = 'editar' | 'agregar' | 'cobrador' | { estado: EstadoRecorrido; titulo: string; pideMotivo: boolean } | null

export function FichaRecorrido() {
  const { code = '' } = useParams()
  const { api, puede } = useSesion()
  const [recorrido, setRecorrido] = useState<Recorrido | null>(null)
  const [paradas, setParadas] = useState<ParadaRecorrido[]>([])
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [dialogo, setDialogo] = useState<Dialogo>(null)
  const ruta = `recorridos/${encodeURIComponent(code)}/`
  const gestiona = puede('recorridos.gestionar')
  const editable = gestiona && !!recorrido && (recorrido.estado === 'planificado' || recorrido.estado === 'abierto')

  const cargar = useCallback(async () => {
    try {
      const [r, p] = await Promise.all([api.get<Recorrido>(ruta), api.get<ParadaRecorrido[]>(`${ruta}conexiones/`)])
      setRecorrido(r.data)
      setParadas(p.data)
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }, [api, ruta])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function accion(sub: string, cuerpo: object, mensaje: string) {
    setError('')
    setAviso('')
    try {
      await api.post(`${ruta}${sub}/`, cuerpo)
      setAviso(mensaje)
      await cargar()
      return true
    } catch (e) {
      setError(mensajeDeError(e))
      return false
    }
  }

  async function mover(indice: number, delta: number) {
    const codes = paradas.map((p) => p.conexion)
    const destino = indice + delta
    if (destino < 0 || destino >= codes.length) return
    ;[codes[indice], codes[destino]] = [codes[destino], codes[indice]]
    setParadas(codes.map((c) => paradas.find((p) => p.conexion === c)!))
    await accion('ordenar', { conexiones: codes }, 'Orden actualizado.')
  }

  if (!recorrido) return error ? <Aviso tipo="error">{error}</Aviso> : <p className="text-koape-gris">Cargando…</p>
  const botonesEstado: { estado: EstadoRecorrido; titulo: string; pideMotivo: boolean }[] = {
    planificado: [{ estado: 'abierto' as const, titulo: 'Abrir', pideMotivo: false }, { estado: 'anulado' as const, titulo: 'Anular', pideMotivo: true }],
    abierto: [{ estado: 'cerrado' as const, titulo: 'Cerrar', pideMotivo: false }],
    cerrado: [{ estado: 'abierto' as const, titulo: 'Reabrir', pideMotivo: true }],
    anulado: [],
  }[recorrido.estado]

  return (
    <div className="max-w-5xl space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm"><Link className="text-koape-rojo hover:underline" to="/panel/recorridos">← Recorridos</Link></p>
          <h1 className="text-2xl font-extrabold">{recorrido.nombre}</h1>
          <p className="text-sm text-koape-gris">{recorrido.Code} · período {recorrido.periodo}
            {recorrido.fecha_desde || recorrido.fecha_hasta ? ` · ${recorrido.fecha_desde ?? '…'} a ${recorrido.fecha_hasta ?? '…'}` : ''}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <InsigniaRecorrido r={recorrido} />
          {gestiona && recorrido.estado !== 'anulado' && <button className="boton-secundario" onClick={() => setDialogo('editar')}>Editar</button>}
          {gestiona && botonesEstado.map((b) => (
            <button key={b.titulo} className={b.estado === 'anulado' ? 'boton-secundario' : 'boton-primario'} onClick={() => setDialogo(b)}>{b.titulo}</button>
          ))}
        </div>
      </div>
      <Aviso tipo="error">{error}</Aviso>
      <Aviso tipo="exito">{aviso}</Aviso>

      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <section className="tarjeta p-5">
          <h2 className="mb-2 text-lg font-bold">Avance</h2>
          <BarraAvance a={recorrido.avance} />
          {recorrido.estado === 'planificado' && <p className="mt-3 text-xs text-koape-gris">Para que los cobradores lo vean en el celular: agregue conexiones, asigne cobradores y <b>Abra</b> el recorrido.</p>}
        </section>
        <section className="tarjeta p-5">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-lg font-bold">Cobradores</h2>
            {editable && <button className="text-sm font-semibold text-koape-rojo hover:underline" onClick={() => setDialogo('cobrador')}>Asignar</button>}
          </div>
          <ul className="space-y-2 text-sm">
            {recorrido.cobradores.filter((c) => c.activa).map((c) => (
              <li key={c.usuario} className="flex items-start justify-between gap-2">
                <span><b>{c.nombre}</b> <span className="text-xs text-koape-gris">({c.usuario})</span><br />
                  <span className="text-xs text-koape-gris">{c.iniciado_en ? `Inició ${fechaHora(c.iniciado_en)}` : 'Sin iniciar'}{c.finalizado_en ? ` · finalizó ${fechaHora(c.finalizado_en)}` : ''}</span></span>
                {gestiona && recorrido.estado !== 'anulado' && <button className="text-xs font-semibold text-koape-gris hover:text-koape-rojo" onClick={() => void accion('retirar-cobrador', { usuario: c.usuario }, 'Cobrador retirado.')}>Retirar</button>}
              </li>
            ))}
            {!recorrido.cobradores.some((c) => c.activa) && <li className="text-koape-gris">Sin cobradores.</li>}
          </ul>
        </section>
      </div>

      <section className="tarjeta p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-bold">Conexiones en orden de visita ({paradas.length})</h2>
          {editable && <button className="boton-primario" onClick={() => setDialogo('agregar')}>Agregar conexiones</button>}
        </div>
        <div className="overflow-x-auto">
          <table className="tabla">
            <thead><tr><th>#</th><th>Conexión</th><th>Titular</th><th>Dirección</th><th>Medidor</th><th>Lectura</th><th /></tr></thead>
            <tbody>
              {paradas.map((p, i) => (
                <tr key={p.conexion}>
                  <td className="whitespace-nowrap">
                    {gestiona && recorrido.estado !== 'anulado' ? (
                      <span className="inline-flex items-center gap-1">
                        <button className="px-1 text-koape-gris hover:text-koape-tinta disabled:opacity-30" disabled={i === 0} onClick={() => void mover(i, -1)} aria-label="Subir">▲</button>
                        <button className="px-1 text-koape-gris hover:text-koape-tinta disabled:opacity-30" disabled={i === paradas.length - 1} onClick={() => void mover(i, 1)} aria-label="Bajar">▼</button>
                        {i + 1}
                      </span>
                    ) : i + 1}
                  </td>
                  <td><Link className="font-semibold text-koape-rojo hover:underline" to={`/panel/conexiones/${p.conexion}`}>{p.conexion}</Link></td>
                  <td>{p.titular}</td>
                  <td>{p.direccion || '—'}{p.barrio ? <span className="text-xs text-koape-gris"> · {p.barrio}</span> : null}</td>
                  <td>{p.medidor ? <>{p.medidor}{p.medidor_numero && <span className="block font-mono text-xs text-koape-gris">N.º {p.medidor_numero}</span>}</> : <span className="text-koape-rojo">Sin medidor</span>}</td>
                  <td>{p.lectura ? <Link className="hover:underline" to={`/panel/lecturas/${p.lectura.comprobante}`}>{p.lectura.estado_nombre}</Link> : <span className="text-koape-gris">Pendiente</span>}</td>
                  <td className="text-right">{editable && !p.lectura && <button className="text-xs font-semibold text-koape-gris hover:text-koape-rojo" onClick={() => void accion('quitar-conexion', { conexion: p.conexion }, 'Conexión quitada.')}>Quitar</button>}</td>
                </tr>
              ))}
              {paradas.length === 0 && <tr><td colSpan={7} className="text-center text-koape-gris">Todavía no tiene conexiones.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      {dialogo === 'editar' && <FormularioRecorrido recorrido={recorrido} alCerrar={() => setDialogo(null)} alGuardar={() => { setDialogo(null); void cargar() }} />}
      {dialogo === 'agregar' && <DialogoAgregar ruta={ruta} alCerrar={() => setDialogo(null)} alListo={(m) => { setDialogo(null); setAviso(m); void cargar() }} />}
      {dialogo === 'cobrador' && <DialogoCobrador asignados={recorrido.cobradores.filter((c) => c.activa).map((c) => c.usuario)} alCerrar={() => setDialogo(null)}
        alElegir={async (u) => { if (await accion('asignar-cobrador', { usuario: u }, 'Cobrador asignado.')) setDialogo(null) }} />}
      {dialogo && typeof dialogo === 'object' && (
        <DialogoEstado titulo={`${dialogo.titulo} el recorrido`} pideMotivo={dialogo.pideMotivo} alCerrar={() => setDialogo(null)}
          alConfirmar={async (motivo) => { if (await accion('estado', { estado: dialogo.estado, motivo }, 'Estado actualizado.')) setDialogo(null) }} />
      )}
    </div>
  )
}

function DialogoAgregar({ ruta, alCerrar, alListo }: { ruta: string; alCerrar: () => void; alListo: (mensaje: string) => void }) {
  const { api } = useSesion()
  const { zonas, barrios } = useTerritorio()
  const [modo, setModo] = useState<'zona' | 'barrio' | 'conexiones'>('barrio')
  const [valor, setValor] = useState('')
  const [error, setError] = useState('')

  async function agregar(e: FormEvent) {
    e.preventDefault()
    setError('')
    const cuerpo = modo === 'conexiones' ? { conexiones: valor.split(/[\s,;]+/).filter(Boolean) } : { [modo]: valor }
    try {
      const r = await api.post<{ agregadas: string[]; sin_medidor: string[]; en_otro_recorrido: { conexion: string; recorrido: string }[] }>(`${ruta}agregar-conexiones/`, cuerpo)
      const d = r.data
      const partes = [`${d.agregadas.length} agregada(s)`]
      if (d.sin_medidor.length) partes.push(`${d.sin_medidor.length} sin medidor: ${d.sin_medidor.join(', ')}`)
      if (d.en_otro_recorrido.length) partes.push(`ya en otro recorrido del período: ${d.en_otro_recorrido.map((x) => `${x.conexion} (${x.recorrido})`).join(', ')}`)
      alListo(partes.join(' · '))
    } catch (err) {
      setError(mensajeDeError(err))
    }
  }

  return (
    <Modal titulo="Agregar conexiones" alCerrar={alCerrar}>
      <form className="space-y-4" onSubmit={agregar}>
        <Aviso tipo="error">{error}</Aviso>
        <div className="flex gap-2 text-sm">
          {(['zona', 'barrio', 'conexiones'] as const).map((m) => (
            <button key={m} type="button" onClick={() => { setModo(m); setValor('') }}
              className={`rounded-full border px-3 py-1 font-semibold ${modo === m ? 'border-koape-tinta bg-koape-tinta text-white' : 'border-koape-gris-claro'}`}>
              {{ zona: 'Por zona', barrio: 'Por barrio', conexiones: 'Por códigos' }[m]}
            </button>
          ))}
        </div>
        {modo === 'zona' && (
          <select className="campo" value={valor} onChange={(e) => setValor(e.target.value)}>
            <option value="">Elegir zona…</option>
            {zonas.filter((z) => z.activa).map((z) => <option key={z.Code} value={z.Code}>{z.nombre}</option>)}
          </select>
        )}
        {modo === 'barrio' && (
          <select className="campo" value={valor} onChange={(e) => setValor(e.target.value)}>
            <option value="">Elegir barrio…</option>
            {barrios.filter((b) => b.activo).map((b) => <option key={b.Code} value={b.Code}>{b.zona_nombre} / {b.nombre}</option>)}
          </select>
        )}
        {modo === 'conexiones' && <textarea className="campo min-h-24 uppercase" value={valor} onChange={(e) => setValor(e.target.value)} placeholder="Códigos de conexión separados por espacio, coma o renglón" />}
        <p className="text-xs text-koape-gris">Se agregan al final, en orden de barrio y dirección; después puede reordenarlas. Solo entran las conexiones en servicio con medidor instalado.</p>
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={!valor.trim()}>Agregar</button>
        </div>
      </form>
    </Modal>
  )
}

function DialogoCobrador({ asignados, alCerrar, alElegir }: { asignados: string[]; alCerrar: () => void; alElegir: (usuario: string) => void }) {
  const { api } = useSesion()
  const [lista, setLista] = useState<{ usuario: string; nombre: string }[] | null>(null)
  useEffect(() => {
    api.get<{ usuario: string; nombre: string }[]>('recorridos/cobradores/').then((r) => setLista(r.data)).catch(() => setLista([]))
  }, [api])
  const libres = (lista ?? []).filter((c) => !asignados.includes(c.usuario))
  return (
    <Modal titulo="Asignar cobrador" alCerrar={alCerrar}>
      {!lista ? <p className="text-sm text-koape-gris">Cargando…</p> : libres.length === 0 ? (
        <p className="text-sm text-koape-gris">No hay más usuarios con el permiso «Tomar lecturas». Asígneles el rol Cobrador en Usuarios.</p>
      ) : (
        <ul className="divide-y divide-koape-gris-claro/50">
          {libres.map((c) => (
            <li key={c.usuario} className="flex items-center justify-between py-2 text-sm">
              <span><b>{c.nombre}</b> <span className="text-koape-gris">({c.usuario})</span></span>
              <button className="boton-secundario" onClick={() => alElegir(c.usuario)}>Asignar</button>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  )
}

export function DialogoEstado({ titulo, pideMotivo, alCerrar, alConfirmar }: { titulo: string; pideMotivo: boolean; alCerrar: () => void; alConfirmar: (motivo: string) => void }) {
  const [motivo, setMotivo] = useState('')
  return (
    <Modal titulo={titulo} alCerrar={alCerrar}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); alConfirmar(motivo) }}>
        <Campo etiqueta={pideMotivo ? 'Motivo (obligatorio, queda en la auditoría)' : 'Motivo (opcional)'}>
          <textarea className="campo" value={motivo} onChange={(e) => setMotivo(e.target.value)} />
        </Campo>
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={pideMotivo && !motivo.trim()}>Confirmar</button>
        </div>
      </form>
    </Modal>
  )
}
