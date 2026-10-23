import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { mensajeDeError } from '../../api/cliente'
import type { ConceptoTarifa, ResultadoCalculo, Tarifa, TasaIva, TipoConcepto, VersionTarifa } from '../../api/tipos'
import { Aviso } from '../../componentes/Aviso'
import { Campo } from '../../componentes/Campo'
import { Encabezado } from '../../componentes/Encabezado'
import { Modal } from '../../componentes/Modal'
import { useSesion } from '../../sesion/ContextoSesion'
import { periodoActual } from '../lecturas/Recorridos'

export const gs = (v: string | number | null | undefined) =>
  v === null || v === undefined || v === '' ? '—' : `Gs. ${Number(v).toLocaleString('es-PY', { maximumFractionDigits: 0 })}`
export const num = (v: string | number | null | undefined) =>
  v === null || v === undefined || v === '' ? '—' : Number(v).toLocaleString('es-PY', { maximumFractionDigits: 3 })

export const TIPOS: Record<TipoConcepto, string> = {
  minimo: 'Consumo mínimo', excedente: 'Excedente por m³', tramo: 'Tramo de consumo', por_m3: 'Precio por m³',
  fijo: 'Cargo fijo', porcentaje: 'Porcentaje (ej. ERSSAN)',
}
const IVAS: Record<TasaIva, string> = { '10': 'IVA 10 %', '5': 'IVA 5 %', exento: 'Exento' }

function describir(c: ConceptoTarifa): string {
  switch (c.tipo) {
    case 'minimo': return `${num(c.cantidad)} m³ a ${gs(c.precio)} c/u (se cobra se use o no)`
    case 'excedente': return `${gs(c.precio)} por m³ sobre el mínimo`
    case 'tramo': return `de ${num(c.desde)} a ${c.hasta ? num(c.hasta) : 'más'} m³: ${gs(c.precio)} por m³`
    case 'por_m3': return `${gs(c.precio)} por m³`
    case 'fijo': return `${gs(c.precio)} por mes`
    case 'porcentaje': return `${num(c.porcentaje)} % del servicio sin impuestos`
  }
}

export function Tarifas() {
  const { api, puede } = useSesion()
  const [tarifas, setTarifas] = useState<Tarifa[]>([])
  const [error, setError] = useState('')
  const [editando, setEditando] = useState<Tarifa | 'nueva' | null>(null)
  const [version, setVersion] = useState<{ tarifa: Tarifa; version: VersionTarifa | null; base?: VersionTarifa } | null>(null)
  const [simular, setSimular] = useState<Tarifa | null>(null)
  const gestiona = puede('tarifas.gestionar')

  const cargar = useCallback(async () => {
    try {
      setTarifas((await api.get<Tarifa[]>('tarifas/')).data)
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }, [api])
  useEffect(() => { void cargar() }, [cargar])

  const listo = () => { setEditando(null); setVersion(null); void cargar() }

  return (
    <div>
      <Encabezado titulo="Tarifas"
        descripcion="Una tarifa por tipo de conexión. Cada tarifa tiene versiones con vigencia; los precios no incluyen IVA."
        acciones={gestiona && <button className="boton-primario" onClick={() => setEditando('nueva')}>Nueva tarifa</button>} />
      <Aviso tipo="error">{error}</Aviso>
      {tarifas.length === 0 && <p className="text-sm text-koape-gris">Todavía no hay tarifas. Sin tarifa vigente, las lecturas quedan sin liquidar.</p>}
      <div className="space-y-4">
        {tarifas.map((t) => {
          const vigente = t.versiones.find((v) => v.vigente_desde <= periodoActual())
          return (
            <div key={t.Code} className={`tarjeta p-5 ${t.activa ? '' : 'opacity-60'}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-titulo text-lg font-bold">{t.nombre} <span className="text-sm font-normal text-koape-gris">{t.Code}</span>
                    {t.por_defecto && <span className="ml-2 rounded-full bg-koape-tinta px-2 py-0.5 text-xs text-white">por defecto</span>}</p>
                  <p className="text-xs text-koape-gris">{t.descripcion || ''}{t.por_defecto ? ' · la usan las conexiones sin tarifa asignada' : ` · ${t.cantidad_conexiones} conexión(es)`}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button className="boton-secundario" onClick={() => setSimular(t)} disabled={!t.versiones.length}>Simular</button>
                  {gestiona && <button className="boton-secundario" onClick={() => setEditando(t)}>Editar</button>}
                  {gestiona && <button className="boton-primario" onClick={() => setVersion({ tarifa: t, version: null, base: vigente ?? t.versiones[0] })}>Nueva versión</button>}
                </div>
              </div>
              {t.versiones.length === 0 && <p className="mt-3 text-sm text-koape-rojo">Sin versiones: cargue los conceptos y precios con «Nueva versión».</p>}
              <div className="mt-3 space-y-3">
                {t.versiones.map((v) => (
                  <div key={v.vigente_desde} className="rounded-lg border border-koape-gris-claro p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-bold">Vigente desde {v.vigente_desde}
                        {v === vigente && <span className="ml-2 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">vigente</span>}
                        {v.usada && <span className="ml-2 text-xs font-normal text-koape-gris">· usada en liquidaciones (no se modifica)</span>}</p>
                      {gestiona && !v.usada && <button className="text-sm font-semibold text-koape-rojo hover:underline" onClick={() => setVersion({ tarifa: t, version: v })}>Modificar</button>}
                    </div>
                    {v.observaciones && <p className="text-xs text-koape-gris">{v.observaciones}</p>}
                    <ul className="mt-2 space-y-1 text-sm">
                      {v.conceptos.map((c) => (
                        <li key={`${c.orden}-${c.nombre}`} className="flex flex-wrap justify-between gap-2">
                          <span><b>{c.nombre}</b> <span className="text-koape-gris">· {describir(c)}</span></span>
                          <span className="text-xs text-koape-gris">{IVAS[c.iva]}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
      {editando && <FormularioTarifa tarifa={editando === 'nueva' ? null : editando} alCerrar={() => setEditando(null)} alGuardar={listo} />}
      {version && <EditorVersion {...version} alCerrar={() => setVersion(null)} alGuardar={listo} />}
      {simular && <Simulador tarifa={simular} alCerrar={() => setSimular(null)} />}
    </div>
  )
}

function FormularioTarifa({ tarifa, alCerrar, alGuardar }: { tarifa: Tarifa | null; alCerrar: () => void; alGuardar: () => void }) {
  const { api } = useSesion()
  const [form, setForm] = useState({
    Code: tarifa?.Code ?? '', nombre: tarifa?.nombre ?? '', descripcion: tarifa?.descripcion ?? '',
    por_defecto: tarifa?.por_defecto ?? false, activa: tarifa?.activa ?? true,
  })
  const [error, setError] = useState('')
  async function guardar(e: FormEvent) {
    e.preventDefault()
    setError('')
    try {
      if (tarifa) await api.patch(`tarifas/${tarifa.Code}/`, form)
      else await api.post('tarifas/', form)
      alGuardar()
    } catch (err) {
      setError(mensajeDeError(err))
    }
  }
  return (
    <Modal titulo={tarifa ? `Tarifa ${tarifa.Code}` : 'Nueva tarifa (tipo de conexión)'} alCerrar={alCerrar}>
      <form onSubmit={guardar} className="space-y-4">
        <Aviso tipo="error">{error}</Aviso>
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo etiqueta="Código"><input className="campo uppercase" required maxLength={40} disabled={!!tarifa} value={form.Code} onChange={(e) => setForm({ ...form, Code: e.target.value })} placeholder="Ej. RES" /></Campo>
          <Campo etiqueta="Tipo de conexión"><input className="campo" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} placeholder="Ej. Residencial" /></Campo>
          <Campo etiqueta="Descripción" ancho><input className="campo" value={form.descripcion} onChange={(e) => setForm({ ...form, descripcion: e.target.value })} /></Campo>
        </div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.por_defecto} onChange={(e) => setForm({ ...form, por_defecto: e.target.checked })} /> Por defecto (para las conexiones sin tarifa asignada)</label>
        {tarifa && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.activa} onChange={(e) => setForm({ ...form, activa: e.target.checked })} /> Activa</label>}
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={!form.Code.trim() || !form.nombre.trim()}>Guardar</button>
        </div>
      </form>
    </Modal>
  )
}

type Fila = { nombre: string; tipo: TipoConcepto; cantidad: string; desde: string; hasta: string; precio: string; porcentaje: string; iva: TasaIva }
const aTexto = (v: string | null) => (v === null ? '' : Number(v).toLocaleString('es-PY', { maximumFractionDigits: 3 }))
const filaDe = (c: ConceptoTarifa): Fila => ({
  nombre: c.nombre, tipo: c.tipo, cantidad: aTexto(c.cantidad), desde: aTexto(c.desde), hasta: aTexto(c.hasta),
  precio: aTexto(c.precio), porcentaje: aTexto(c.porcentaje), iva: c.iva,
})
const EJEMPLO: Fila[] = [
  { nombre: 'Consumo mínimo', tipo: 'minimo', cantidad: '10', desde: '', hasta: '', precio: '', porcentaje: '', iva: '10' },
  { nombre: 'Excedente', tipo: 'excedente', cantidad: '', desde: '', hasta: '', precio: '', porcentaje: '', iva: '10' },
  { nombre: 'Tasa ERSSAN', tipo: 'porcentaje', cantidad: '', desde: '', hasta: '', precio: '', porcentaje: '2', iva: 'exento' },
]
/** Número escrito como en Paraguay: «2.500» o «1.234,5» (punto de miles, coma decimal). */
const numeroPy = (v: string) => {
  const t = v.trim().replace(/\s/g, '')
  if (t === '') return null
  return t.replace(/\./g, '').replace(',', '.')
}

function EditorVersion({ tarifa, version, base, alCerrar, alGuardar }: { tarifa: Tarifa; version: VersionTarifa | null; base?: VersionTarifa; alCerrar: () => void; alGuardar: () => void }) {
  const { api } = useSesion()
  const [vigente, setVigente] = useState(version?.vigente_desde ?? periodoActual())
  const [observaciones, setObservaciones] = useState(version?.observaciones ?? '')
  const [filas, setFilas] = useState<Fila[]>(() => (version ?? base)?.conceptos.map(filaDe) ?? EJEMPLO)
  const [error, setError] = useState('')
  const cambiar = (i: number, cambio: Partial<Fila>) => setFilas(filas.map((f, n) => (n === i ? { ...f, ...cambio } : f)))

  async function guardar(e: FormEvent) {
    e.preventDefault()
    setError('')
    const conceptos = filas.map((f, n) => ({
      orden: n, nombre: f.nombre, tipo: f.tipo, iva: f.iva, cantidad: numeroPy(f.cantidad), desde: numeroPy(f.desde),
      hasta: numeroPy(f.hasta), precio: numeroPy(f.precio), porcentaje: numeroPy(f.porcentaje),
    }))
    try {
      if (version) await api.patch(`tarifas/${tarifa.Code}/versiones/${version.vigente_desde}/`, { conceptos, observaciones })
      else await api.post(`tarifas/${tarifa.Code}/versiones/`, { vigente_desde: vigente, observaciones, conceptos })
      alGuardar()
    } catch (err) {
      setError(mensajeDeError(err))
    }
  }

  return (
    <Modal titulo={`${tarifa.nombre}: ${version ? `versión desde ${version.vigente_desde}` : 'nueva versión'}`} alCerrar={alCerrar} amplio>
      <form onSubmit={guardar} className="space-y-4">
        <Aviso tipo="error">{error}</Aviso>
        <div className="grid gap-4 sm:grid-cols-[180px_1fr]">
          <Campo etiqueta="Vigente desde (período)"><input type="month" className="campo" required disabled={!!version} value={vigente} onChange={(e) => setVigente(e.target.value)} /></Campo>
          <Campo etiqueta="Observaciones"><input className="campo" value={observaciones} onChange={(e) => setObservaciones(e.target.value)} placeholder="Ej. resolución o acta que la aprueba" /></Campo>
        </div>
        <p className="text-xs text-koape-gris">Números como en Paraguay: punto de miles y coma decimal (ej. 2.500 o 2,5). Los precios se cargan <b>sin IVA</b> (el IVA se calcula aparte). El porcentaje se aplica sobre la suma de los demás conceptos (el servicio sin impuestos).</p>
        <div className="space-y-2">
          {filas.map((f, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2 rounded-lg border border-koape-gris-claro p-3 [&>input]:w-32 [&>select]:w-auto">
              <input className="campo flex-1 !w-auto min-w-48" placeholder="Nombre en la factura" value={f.nombre} onChange={(e) => cambiar(i, { nombre: e.target.value })} />
              <select className="campo" value={f.tipo} onChange={(e) => cambiar(i, { tipo: e.target.value as TipoConcepto })}>
                {Object.entries(TIPOS).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
              </select>
              {f.tipo === 'minimo' && <input className="campo" inputMode="decimal" placeholder="m³ mínimo" value={f.cantidad} onChange={(e) => cambiar(i, { cantidad: e.target.value })} />}
              {f.tipo === 'tramo' && <>
                <input className="campo" inputMode="decimal" placeholder="desde m³" value={f.desde} onChange={(e) => cambiar(i, { desde: e.target.value })} />
                <input className="campo" inputMode="decimal" placeholder="hasta m³ (vacío: más)" value={f.hasta} onChange={(e) => cambiar(i, { hasta: e.target.value })} />
              </>}
              {f.tipo === 'porcentaje'
                ? <input className="campo" inputMode="decimal" placeholder="%" value={f.porcentaje} onChange={(e) => cambiar(i, { porcentaje: e.target.value })} />
                : <input className="campo" inputMode="decimal" placeholder={f.tipo === 'fijo' ? 'Monto Gs.' : 'Gs. por m³'} value={f.precio} onChange={(e) => cambiar(i, { precio: e.target.value })} />}
              <select className="campo" value={f.iva} onChange={(e) => cambiar(i, { iva: e.target.value as TasaIva })}>
                {Object.entries(IVAS).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
              </select>
              <button type="button" className="text-sm font-semibold text-koape-gris hover:text-koape-rojo" onClick={() => setFilas(filas.filter((_, n) => n !== i))}>Quitar</button>
            </div>
          ))}
          <button type="button" className="boton-secundario" onClick={() => setFilas([...filas, { nombre: '', tipo: 'fijo', cantidad: '', desde: '', hasta: '', precio: '', porcentaje: '', iva: '10' }])}>+ Agregar concepto</button>
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={!filas.length}>Guardar versión</button>
        </div>
      </form>
    </Modal>
  )
}

export function TablaCalculo({ r }: { r: ResultadoCalculo }) {
  return (
    <div className="overflow-x-auto">
      <table className="tabla">
        <thead><tr><th>Concepto</th><th>Cantidad</th><th>Precio</th><th>IVA</th><th className="text-right">Importe</th></tr></thead>
        <tbody>
          {r.lineas.map((l, n) => (
            <tr key={n}>
              <td>{l.concepto}</td>
              <td>{l.tipo === 'porcentaje' ? gs(l.cantidad) : l.tipo === 'fijo' ? '1' : `${num(l.cantidad)} m³`}</td>
              <td>{l.tipo === 'porcentaje' ? `${num(l.precio)} %` : gs(l.precio)}</td>
              <td>{IVAS[l.iva]}</td>
              <td className="text-right">{gs(l.importe)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot className="text-sm">
          {Number(r.subtotal_exento) > 0 && <tr><td colSpan={4}>Subtotal exento</td><td className="text-right">{gs(r.subtotal_exento)}</td></tr>}
          {Number(r.subtotal_iva5) > 0 && <tr><td colSpan={4}>Subtotal gravado 5 % · IVA 5 %</td><td className="text-right">{gs(r.subtotal_iva5)} · {gs(r.iva5)}</td></tr>}
          {Number(r.subtotal_iva10) > 0 && <tr><td colSpan={4}>Subtotal gravado 10 % · IVA 10 %</td><td className="text-right">{gs(r.subtotal_iva10)} · {gs(r.iva10)}</td></tr>}
          <tr className="font-extrabold"><td colSpan={4}>Total</td><td className="text-right text-lg">{gs(r.total)}</td></tr>
        </tfoot>
      </table>
    </div>
  )
}

function Simulador({ tarifa, alCerrar }: { tarifa: Tarifa; alCerrar: () => void }) {
  const { api } = useSesion()
  const [periodo, setPeriodo] = useState(periodoActual())
  const [consumo, setConsumo] = useState('15')
  const [resultado, setResultado] = useState<ResultadoCalculo | null>(null)
  const [error, setError] = useState('')
  async function calcularAhora(e?: FormEvent) {
    e?.preventDefault()
    setError('')
    try {
      setResultado((await api.post<ResultadoCalculo>(`tarifas/${tarifa.Code}/simular/`, { periodo, consumo: numeroPy(consumo) })).data)
    } catch (err) {
      setResultado(null)
      setError(mensajeDeError(err))
    }
  }
  return (
    <Modal titulo={`Simular ${tarifa.nombre}`} alCerrar={alCerrar} amplio>
      <form onSubmit={calcularAhora} className="mb-4 flex flex-wrap items-end gap-3">
        <Campo etiqueta="Período"><input type="month" className="campo" value={periodo} onChange={(e) => setPeriodo(e.target.value)} /></Campo>
        <Campo etiqueta="Consumo (m³)"><input className="campo" inputMode="decimal" value={consumo} onChange={(e) => setConsumo(e.target.value)} /></Campo>
        <button className="boton-primario">Calcular</button>
      </form>
      <Aviso tipo="error">{error}</Aviso>
      {resultado && <><p className="mb-2 text-xs text-koape-gris">Versión vigente desde {resultado.version}. No se guarda nada.</p><TablaCalculo r={resultado} /></>}
    </Modal>
  )
}
