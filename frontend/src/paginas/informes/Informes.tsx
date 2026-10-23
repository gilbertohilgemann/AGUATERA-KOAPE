import axios from 'axios'
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { mensajeDeError } from '../../api/cliente'
import type { Barrio, ColumnaInforme, CredencialIntegracion, DatosInforme, InformeCatalogo, SeccionPanel, Zona } from '../../api/tipos'
import { Aviso } from '../../componentes/Aviso'
import { Campo } from '../../componentes/Campo'
import { Encabezado } from '../../componentes/Encabezado'
import { Modal } from '../../componentes/Modal'
import { useSesion } from '../../sesion/ContextoSesion'
import { fechaHora } from '../../utilidades/fechas'
import { gs } from '../tarifas/Tarifas'

const numero = (v: string | number, decimales = 0) => Number(v).toLocaleString('es-PY', { minimumFractionDigits: decimales, maximumFractionDigits: decimales })

function formatear(valor: string | number | undefined, tipo: ColumnaInforme['tipo']) {
  if (valor === undefined || valor === null || valor === '') return ''
  switch (tipo) {
    case 'gs': return gs(valor)
    case 'numero': return numero(valor)
    case 'decimal': return numero(valor, 2)
    case 'porcentaje': return `${numero(valor, 1)} %`
    case 'fecha': return typeof valor === 'string' && valor.length === 10 ? new Date(`${valor}T12:00:00`).toLocaleDateString('es-PY') : String(valor)
    default: return String(valor)
  }
}
const aDerecha = (tipo: ColumnaInforme['tipo']) => ['gs', 'numero', 'decimal', 'porcentaje'].includes(tipo)

/** Indicadores del inicio: cada uno con su definición (pasando el mouse) y enlace al detalle. */
export function PanelIndicadores({ omitir = [] }: { omitir?: string[] }) {
  const { api } = useSesion()
  const [secciones, setSecciones] = useState<SeccionPanel[]>([])
  useEffect(() => { api.get<SeccionPanel[]>('informes/panel/').then((r) => setSecciones(r.data)).catch(() => setSecciones([])) }, [api])
  return (
    <div className="space-y-4">
      {secciones.filter((s) => !omitir.includes(s.titulo)).map((s) => (
        <section key={s.titulo}>
          <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-koape-gris">{s.titulo}</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {s.indicadores.map((i) => {
              const valor = i.tipo === 'gs' ? gs(i.valor) : i.tipo === 'm3' ? `${numero(i.valor, 1)} m³` : i.tipo === 'numero' ? numero(i.valor) : i.valor
              const contenido = (<><p className="etiqueta">{i.titulo}</p><p className={`font-titulo text-2xl font-extrabold ${i.alerta ? 'text-koape-rojo' : ''}`}>{valor}</p>{i.definicion && <p className="mt-1 text-xs text-koape-gris">{i.definicion}</p>}</>)
              return i.enlace ? <Link key={i.titulo} to={`/panel/${i.enlace}`} className="tarjeta p-4 transition hover:border-koape-magenta">{contenido}</Link> : <div key={i.titulo} className="tarjeta p-4">{contenido}</div>
            })}
          </div>
        </section>
      ))}
    </div>
  )
}

const ESTADOS_CAJA = [['', 'Todas'], ['abierta', 'Abiertas'], ['en_revision', 'En revisión'], ['cerrada', 'Cerradas']]

export function Informes() {
  const { api } = useSesion()
  const [catalogo, setCatalogo] = useState<InformeCatalogo[]>([])
  const [elegido, setElegido] = useState<InformeCatalogo | null>(null)
  const [filtros, setFiltros] = useState<Record<string, string>>({})
  const [datos, setDatos] = useState<DatosInforme | null>(null)
  const [zonas, setZonas] = useState<Zona[]>([])
  const [barrios, setBarrios] = useState<Barrio[]>([])
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)

  useEffect(() => {
    api.get<InformeCatalogo[]>('informes/').then((r) => { setCatalogo(r.data); setElegido((e) => e ?? r.data[0] ?? null) }).catch((e) => setError(mensajeDeError(e)))
    api.get<Zona[]>('zonas/').then((r) => setZonas(r.data)).catch(() => setZonas([]))
    api.get<Barrio[]>('barrios/').then((r) => setBarrios(r.data)).catch(() => setBarrios([]))
  }, [api])

  // Solo vale la respuesta de la ÚLTIMA consulta (si se cambia de informe rápido, la anterior se descarta).
  const ultima = useRef(0)
  // Lo que se exporta es exactamente lo que está a la vista (los filtros de la última consulta que respondió).
  const consultados = useRef<Record<string, string>>({})

  const consultar = useCallback(async (informe: InformeCatalogo, valores: Record<string, string>) => {
    const numero = ++ultima.current
    setCargando(true)
    setError('')
    try {
      const params = Object.fromEntries(Object.entries(valores).filter(([, v]) => v))
      const r = await api.get<DatosInforme>(`informes/${informe.codigo}/`, { params })
      if (numero !== ultima.current) return
      consultados.current = params
      setDatos(r.data)
      // Muestra los valores por defecto que aplicó el servidor (ej. el mes en curso) en los filtros vacíos.
      const usados = Object.fromEntries(Object.entries(r.data.filtros).filter(([k]) => informe.filtros.includes(k) || k === 'agrupar'))
      setFiltros({ ...usados, ...params })
    } catch (e) {
      if (numero !== ultima.current) return
      setError(mensajeDeError(e))
      setDatos(null)
    } finally {
      if (numero === ultima.current) setCargando(false)
    }
  }, [api])

  useEffect(() => {
    // Al cambiar de informe: filtros nuevos (nunca los del informe anterior) y una consulta, una sola vez.
    setDatos(null)
    if (!elegido) return
    const iniciales: Record<string, string> = elegido.agrupaciones.length ? { agrupar: elegido.agrupaciones[0].valor } : {}
    setFiltros(iniciales)
    void consultar(elegido, iniciales)
  }, [elegido, consultar])

  async function exportar(formato: 'xlsx' | 'csv') {
    if (!elegido || !datos) return
    setError('')
    try {
      const params = { ...consultados.current, formato }
      const r = await api.get<Blob>(`informes/${elegido.codigo}/`, { params, responseType: 'blob' })
      const url = URL.createObjectURL(r.data)
      const enlace = document.createElement('a')
      enlace.href = url
      enlace.download = `${elegido.codigo}-${new Date().toLocaleDateString('en-CA')}.${formato}`
      enlace.click()
      setTimeout(() => URL.revokeObjectURL(url), 30_000)
    } catch (e) {
      // Con responseType blob el error también llega como Blob: se lee para mostrar el mensaje del servidor.
      const cuerpo = axios.isAxiosError(e) ? e.response?.data : undefined
      if (cuerpo instanceof Blob) {
        try { setError((JSON.parse(await cuerpo.text()) as { detalle?: string }).detalle ?? mensajeDeError(e)); return } catch { /* no es JSON */ }
      }
      setError(mensajeDeError(e))
    }
  }

  const f = (k: string) => filtros[k] ?? ''
  const poner = (k: string, v: string) => setFiltros({ ...filtros, [k]: v })
  const tiene = (k: string) => !!elegido?.filtros.includes(k)
  const grupos = [...new Set(catalogo.map((i) => i.grupo))]

  return (
    <div className="grid gap-6 lg:grid-cols-[16rem_1fr]">
      <aside className="space-y-4">
        <Encabezado titulo="Informes" />
        {grupos.map((g) => (
          <div key={g}>
            <p className="etiqueta mb-1">{g}</p>
            <ul className="space-y-1">
              {catalogo.filter((i) => i.grupo === g).map((i) => (
                <li key={i.codigo}><button className={`w-full rounded-lg px-3 py-2 text-left text-sm ${elegido?.codigo === i.codigo ? 'bg-koape-rojo font-semibold text-white' : 'hover:bg-koape-fondo'}`} onClick={() => setElegido(i)}>{i.titulo}</button></li>
              ))}
            </ul>
          </div>
        ))}
        {catalogo.length === 0 && !error && <p className="text-sm text-koape-gris">No tiene informes habilitados.</p>}
      </aside>
      <div className="min-w-0 space-y-4">
        <Aviso tipo="error">{error}</Aviso>
        {elegido && (
          <>
            <div>
              <h1 className="text-2xl font-extrabold">{elegido.titulo}</h1>
              <p className="text-sm text-koape-gris"><b>Qué cuenta:</b> {elegido.definicion}</p>
            </div>
            <form className="tarjeta grid gap-3 p-4 sm:grid-cols-3 lg:grid-cols-6" onSubmit={(e: FormEvent) => { e.preventDefault(); void consultar(elegido, filtros) }}>
              {tiene('desde') && <Campo etiqueta="Desde"><input type="date" className="campo" value={f('desde')} onChange={(e) => poner('desde', e.target.value)} /></Campo>}
              {tiene('hasta') && <Campo etiqueta="Hasta"><input type="date" className="campo" value={f('hasta')} onChange={(e) => poner('hasta', e.target.value)} /></Campo>}
              {tiene('periodo_desde') && <Campo etiqueta="Desde el período"><input type="month" className="campo" value={f('periodo_desde')} onChange={(e) => poner('periodo_desde', e.target.value)} /></Campo>}
              {tiene('periodo_hasta') && <Campo etiqueta="Hasta el período"><input type="month" className="campo" value={f('periodo_hasta')} onChange={(e) => poner('periodo_hasta', e.target.value)} /></Campo>}
              {tiene('zona') && (
                <Campo etiqueta="Zona"><select className="campo" value={f('zona')} onChange={(e) => setFiltros({ ...filtros, zona: e.target.value, barrio: '' })}>
                  <option value="">Todas</option>{zonas.map((z) => <option key={z.Code} value={z.Code}>{z.nombre}</option>)}</select></Campo>
              )}
              {tiene('barrio') && (
                <Campo etiqueta="Barrio"><select className="campo" value={f('barrio')} onChange={(e) => poner('barrio', e.target.value)}>
                  <option value="">Todos</option>{barrios.filter((b) => !f('zona') || b.zona === f('zona')).map((b) => <option key={b.Code} value={b.Code}>{b.nombre}</option>)}</select></Campo>
              )}
              {tiene('cobrador') && <Campo etiqueta="Usuario (cobró / cajero)"><input className="campo" placeholder="nombre de usuario" value={f('cobrador')} onChange={(e) => poner('cobrador', e.target.value)} /></Campo>}
              {tiene('estado') && (
                <Campo etiqueta="Estado"><select className="campo" value={f('estado')} onChange={(e) => poner('estado', e.target.value)}>
                  {ESTADOS_CAJA.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></Campo>
              )}
              {elegido.agrupaciones.length > 0 && (
                <Campo etiqueta="Agrupar"><select className="campo" value={f('agrupar')} onChange={(e) => poner('agrupar', e.target.value)}>
                  {elegido.agrupaciones.map((a) => <option key={a.valor} value={a.valor}>{a.texto}</option>)}</select></Campo>
              )}
              <div className="flex flex-wrap items-end gap-2 sm:col-span-3 lg:col-span-6">
                <button className="boton-primario" disabled={cargando}>{cargando ? 'Consultando…' : 'Consultar'}</button>
                <button type="button" className="boton-secundario" disabled={!datos || cargando} onClick={() => void exportar('xlsx')}>Excel</button>
                <button type="button" className="boton-secundario" disabled={!datos || cargando} onClick={() => void exportar('csv')}>CSV</button>
                <span className="text-xs text-koape-gris">Se exporta lo que está a la vista (pulse Consultar después de cambiar filtros).</span>
              </div>
            </form>
            {datos && (
              <div className="tarjeta overflow-x-auto">
                <table className="tabla">
                  <thead><tr>{datos.columnas.map((c) => <th key={c.clave} className={aDerecha(c.tipo) ? 'text-right' : ''}>{c.titulo}</th>)}</tr></thead>
                  <tbody>
                    {datos.filas.map((fila, n) => (
                      <tr key={n}>{datos.columnas.map((c) => <td key={c.clave} className={aDerecha(c.tipo) ? 'text-right' : ''}>{formatear(fila[c.clave], c.tipo)}</td>)}</tr>
                    ))}
                    {datos.filas.length === 0 && <tr><td colSpan={datos.columnas.length} className="text-center text-koape-gris">Sin datos para esos filtros.</td></tr>}
                  </tbody>
                  {datos.totales && datos.filas.length > 0 && (
                    <tfoot><tr className="font-bold">{datos.columnas.map((c, n) => <td key={c.clave} className={aDerecha(c.tipo) ? 'text-right' : ''}>{n === 0 ? 'Total' : c.clave in datos.totales! ? formatear(datos.totales![c.clave], c.tipo) : ''}</td>)}</tr></tfoot>
                  )}
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

/** Credenciales para que otro sistema consulte la API (solo lectura). La clave se muestra una sola vez. */
export function Integraciones() {
  const { api } = useSesion()
  const [lista, setLista] = useState<CredencialIntegracion[]>([])
  const [permisos, setPermisos] = useState<{ codigo: string; descripcion: string }[]>([])
  const [error, setError] = useState('')
  const [nueva, setNueva] = useState(false)
  const [form, setForm] = useState({ nombre: '', permisos: [] as string[], limite_por_minuto: '60', expira_en: '' })
  const [creada, setCreada] = useState<CredencialIntegracion | null>(null)
  const [revocando, setRevocando] = useState<CredencialIntegracion | null>(null)
  const [motivo, setMotivo] = useState('')
  const [registro, setRegistro] = useState<{ prefijo: string; filas: { fecha_hora: string; metodo: string; ruta: string; estado: number; ip: string | null; duracion_ms: number }[] } | null>(null)
  const [procesando, setProcesando] = useState(false)

  const cargar = useCallback(() => { api.get<CredencialIntegracion[]>('integraciones/credenciales/').then((r) => setLista(r.data)).catch((e) => setError(mensajeDeError(e))) }, [api])
  useEffect(() => { cargar(); api.get<{ codigo: string; descripcion: string }[]>('integraciones/permisos/').then((r) => setPermisos(r.data)).catch(() => setPermisos([])) }, [api, cargar])

  async function crear(e: FormEvent) {
    e.preventDefault()
    if (procesando) return
    setProcesando(true)
    setError('')
    try {
      const r = await api.post<CredencialIntegracion>('integraciones/credenciales/', {
        nombre: form.nombre, permisos: form.permisos, limite_por_minuto: Number(form.limite_por_minuto) || 60,
        expira_en: form.expira_en ? new Date(`${form.expira_en}T23:59:59`).toISOString() : null,
      })
      setCreada(r.data)
      setNueva(false)
      setForm({ nombre: '', permisos: [], limite_por_minuto: '60', expira_en: '' })
      cargar()
    } catch (err) { setError(mensajeDeError(err)) } finally { setProcesando(false) }
  }

  async function revocar(e: FormEvent) {
    e.preventDefault()
    if (!revocando) return
    try {
      await api.post(`integraciones/credenciales/${revocando.prefijo}/revocar/`, { motivo })
      setRevocando(null)
      setMotivo('')
      cargar()
    } catch (err) { setError(mensajeDeError(err)) }
  }

  async function verRegistro(c: CredencialIntegracion) {
    try { setRegistro({ prefijo: c.prefijo, filas: (await api.get(`integraciones/credenciales/${c.prefijo}/registro/`)).data }) } catch (err) { setError(mensajeDeError(err)) }
  }

  const alternar = (p: string) => setForm({ ...form, permisos: form.permisos.includes(p) ? form.permisos.filter((x) => x !== p) : [...form.permisos, p] })

  return (
    <div className="max-w-5xl">
      <Encabezado titulo="Integraciones (API)" descripcion="Credenciales para que otro sistema (ej. un sistema contable) CONSULTE los datos de la institución. Son de solo lectura y se pueden revocar en cualquier momento."
        acciones={<button className="boton-primario" onClick={() => setNueva(true)}>Nueva credencial</button>} />
      <Aviso tipo="error">{error}</Aviso>
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Sistema</th><th>Identificador</th><th>Permisos</th><th>Último uso</th><th className="text-right">Usos (30 días)</th><th>Estado</th><th /></tr></thead>
          <tbody>
            {lista.map((c) => (
              <tr key={c.prefijo} className={c.activa ? '' : 'text-koape-gris'}>
                <td className="font-semibold">{c.nombre}</td><td className="font-mono text-xs">{c.prefijo}</td>
                <td className="text-xs">{c.permisos.join(', ')}</td>
                <td>{c.ultimo_uso_en ? fechaHora(c.ultimo_uso_en) : 'nunca'}</td>
                <td className="text-right">{c.usos_30_dias}</td>
                <td>{c.activa ? (c.expira_en ? `Activa hasta ${new Date(c.expira_en).toLocaleDateString('es-PY')}` : 'Activa') : `Revocada (${c.motivo_revocacion})`}</td>
                <td className="whitespace-nowrap text-sm">
                  <button className="text-koape-rojo hover:underline" onClick={() => void verRegistro(c)}>Registro</button>
                  {c.activa && <> · <button className="text-koape-rojo hover:underline" onClick={() => setRevocando(c)}>Revocar</button></>}
                </td>
              </tr>
            ))}
            {lista.length === 0 && <tr><td colSpan={7} className="text-center text-koape-gris">Sin credenciales.</td></tr>}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-koape-gris">Uso: enviar el encabezado <code>Authorization: Clave &lt;clave&gt;</code> a <code>/api/v1/…</code> (ver la documentación de la API). Cada solicitud queda registrada.</p>

      {nueva && (
        <Modal titulo="Nueva credencial de integración" alCerrar={() => setNueva(false)}>
          <form className="space-y-4" onSubmit={(e) => void crear(e)}>
            <Campo etiqueta="Sistema que se conecta"><input className="campo" placeholder="Ej. Sistema contable" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} /></Campo>
            <fieldset className="space-y-1"><legend className="etiqueta">Qué puede consultar</legend>
              {permisos.map((p) => <label key={p.codigo} className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={form.permisos.includes(p.codigo)} onChange={() => alternar(p.codigo)} /> {p.descripcion}</label>)}
            </fieldset>
            <div className="grid gap-3 sm:grid-cols-2">
              <Campo etiqueta="Solicitudes por minuto"><input type="number" min={1} max={600} className="campo" value={form.limite_por_minuto} onChange={(e) => setForm({ ...form, limite_por_minuto: e.target.value })} /></Campo>
              <Campo etiqueta="Vence (opcional)"><input type="date" className="campo" value={form.expira_en} onChange={(e) => setForm({ ...form, expira_en: e.target.value })} /></Campo>
            </div>
            <div className="flex justify-end gap-2"><button type="button" className="boton-secundario" onClick={() => setNueva(false)}>Cancelar</button>
              <button className="boton-primario" disabled={procesando || !form.nombre.trim() || !form.permisos.length}>Crear</button></div>
          </form>
        </Modal>
      )}
      {creada && (
        <Modal titulo="Credencial creada" alCerrar={() => setCreada(null)}>
          <div className="space-y-3">
            <Aviso tipo="error">Copie la clave ahora: por seguridad NO se vuelve a mostrar. Si se pierde, revóquela y cree otra.</Aviso>
            <p className="break-all rounded-lg bg-koape-fondo p-3 font-mono text-sm">{creada.clave}</p>
            <div className="flex justify-end gap-2">
              <button className="boton-secundario" onClick={() => void navigator.clipboard?.writeText(creada.clave ?? '')}>Copiar</button>
              <button className="boton-primario" onClick={() => setCreada(null)}>Ya la guardé</button>
            </div>
          </div>
        </Modal>
      )}
      {revocando && (
        <Modal titulo={`Revocar «${revocando.nombre}»`} alCerrar={() => setRevocando(null)}>
          <form className="space-y-4" onSubmit={(e) => void revocar(e)}>
            <p className="text-sm">El sistema que la usa deja de tener acceso inmediatamente. No se puede deshacer (se crea otra).</p>
            <Campo etiqueta="Motivo (obligatorio)"><textarea className="campo" value={motivo} onChange={(e) => setMotivo(e.target.value)} /></Campo>
            <div className="flex justify-end gap-2"><button type="button" className="boton-secundario" onClick={() => setRevocando(null)}>Cancelar</button>
              <button className="boton-primario" disabled={!motivo.trim()}>Revocar</button></div>
          </form>
        </Modal>
      )}
      {registro && (
        <Modal titulo={`Últimas solicitudes de ${registro.prefijo}`} alCerrar={() => setRegistro(null)}>
          <div className="max-h-96 overflow-auto">
            <table className="tabla text-xs">
              <thead><tr><th>Fecha</th><th>Ruta</th><th>Respuesta</th><th>IP</th></tr></thead>
              <tbody>{registro.filas.map((r, n) => <tr key={n}><td>{fechaHora(r.fecha_hora)}</td><td className="font-mono">{r.metodo} {r.ruta}</td><td>{r.estado}</td><td>{r.ip}</td></tr>)}
                {registro.filas.length === 0 && <tr><td colSpan={4} className="text-center text-koape-gris">Todavía no se usó.</td></tr>}</tbody>
            </table>
          </div>
        </Modal>
      )}
    </div>
  )
}
