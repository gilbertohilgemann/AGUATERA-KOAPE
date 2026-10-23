import axios, { type AxiosInstance } from 'axios'
import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { mensajeDeError } from '../api/cliente'
import { urlApi } from '../api/configuracion'
import { Aviso } from '../componentes/Aviso'
import { Logo } from '../componentes/Logo'
import { Modal } from '../componentes/Modal'
import { PieKoape } from '../componentes/PieKoape'
import { gs, num } from '../paginas/tarifas/Tarifas'
import { fechaHora } from '../utilidades/fechas'
import { nuevoIdentificador } from '../utilidades/identificador'

/**
 * Portal de abonados: la persona consulta su cuenta de agua en TODAS las juntas donde es cliente.
 * Sesión propia (no es un usuario del sistema): token «Portal» guardado solo en esta pestaña.
 */
const CLAVE = 'koape.aguateras.portal'
let enMemoria: string | null = null
const leer = () => { try { return window.sessionStorage.getItem(CLAVE) ?? enMemoria } catch { return enMemoria } }
const guardar = (t: string | null) => {
  enMemoria = t
  try { if (t) window.sessionStorage.setItem(CLAVE, t); else window.sessionStorage.removeItem(CLAVE) } catch { /* en memoria */ }
}

function useApiPortal(alExpirar: () => void): AxiosInstance {
  return useMemo(() => {
    const api = axios.create({ baseURL: urlApi(), timeout: 60_000 })
    api.interceptors.request.use((c) => {
      const t = leer()
      if (t) c.headers.set('Authorization', `Portal ${t}`)
      c.headers.set('X-Id-Solicitud', nuevoIdentificador())
      return c
    })
    api.interceptors.response.use((r) => r, (e) => {
      if (axios.isAxiosError(e) && e.response?.status === 401 && !String(e.config?.url).includes('portal/ingresar')) { guardar(null); alExpirar() }
      return Promise.reject(e)
    })
    return api
  }, [alExpirar])
}

const fecha = (v: string | null) => (v ? new Date(`${String(v).slice(0, 10)}T12:00:00`).toLocaleDateString('es-PY') : '—')

function Marco({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-koape-fondo">
      <header className="border-b border-koape-gris-claro bg-white px-4 py-3"><div className="mx-auto flex max-w-4xl items-center justify-between"><Logo compacto /><span className="text-sm font-semibold text-koape-gris">Portal de abonados</span></div></header>
      <main className="mx-auto w-full max-w-4xl flex-1 p-4">{children}</main>
      <PieKoape />
    </div>
  )
}

export function AppPortal() {
  const navegar = useNavigate()
  const alExpirar = useCallback(() => navegar('/portal', { replace: true }), [navegar])
  const api = useApiPortal(alExpirar)
  return (
    <Routes>
      <Route index element={<Ingreso api={api} />} />
      <Route path="clave" element={<ElegirClave api={api} />} />
      <Route path="cuenta" element={leer() ? <Cuenta api={api} /> : <Navigate to="/portal" replace />} />
      <Route path="cuenta/:codigo" element={leer() ? <Institucion api={api} /> : <Navigate to="/portal" replace />} />
      <Route path="*" element={<Navigate to="/portal" replace />} />
    </Routes>
  )
}

function Ingreso({ api }: { api: AxiosInstance }) {
  const navegar = useNavigate()
  const [modo, setModo] = useState<'ingresar' | 'pin'>('ingresar')
  const [usuario, setUsuario] = useState('')
  const [clave, setClave] = useState('')
  const [documento, setDocumento] = useState('')
  const [correo, setCorreo] = useState('')
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [enviando, setEnviando] = useState(false)

  async function ingresar(e: FormEvent) {
    e.preventDefault()
    setError('')
    setEnviando(true)
    try {
      const r = await api.post<{ token: string; debe_cambiar_clave: boolean }>('portal/ingresar/', { usuario, clave })
      guardar(r.data.token)
      navegar(r.data.debe_cambiar_clave ? '/portal/clave' : '/portal/cuenta', { replace: true })
    } catch (err) { setError(mensajeDeError(err, 'No se pudo ingresar.')) } finally { setEnviando(false) }
  }

  async function pedirPin(e: FormEvent) {
    e.preventDefault()
    setError('')
    setAviso('')
    setEnviando(true)
    try {
      const r = await api.post<{ detalle: string }>('portal/solicitar-pin/', { documento, correo })
      setAviso(r.data.detalle)
      setUsuario(correo)
      setModo('ingresar')
    } catch (err) { setError(mensajeDeError(err)) } finally { setEnviando(false) }
  }

  return (
    <Marco>
      <div className="mx-auto max-w-sm space-y-4 py-6">
        <div>
          <h1 className="text-2xl font-extrabold">Consulte su cuenta de agua</h1>
          <p className="text-sm text-koape-gris">Su deuda, facturas, pagos y lecturas en todas las juntas o aguateras donde es usuario.</p>
        </div>
        <div className="grid grid-cols-2 gap-1 rounded-xl bg-white p-1 text-sm font-semibold">
          <button className={`rounded-lg py-2 ${modo === 'ingresar' ? 'bg-koape-rojo text-white' : ''}`} onClick={() => setModo('ingresar')}>Ingresar</button>
          <button className={`rounded-lg py-2 ${modo === 'pin' ? 'bg-koape-rojo text-white' : ''}`} onClick={() => setModo('pin')}>Activar / olvidé mi clave</button>
        </div>
        <Aviso tipo="error">{error}</Aviso>
        <Aviso tipo="exito">{aviso}</Aviso>
        {modo === 'ingresar' ? (
          <form className="space-y-3 rounded-xl bg-white p-4" onSubmit={(e) => void ingresar(e)}>
            <label className="block text-sm"><span className="etiqueta">Correo o número de documento</span>
              <input className="campo" value={usuario} onChange={(e) => setUsuario(e.target.value)} autoComplete="username" autoCapitalize="none" /></label>
            <label className="block text-sm"><span className="etiqueta">Contraseña (o el PIN que le llegó por correo)</span>
              <input type="password" className="campo" value={clave} onChange={(e) => setClave(e.target.value)} autoComplete="current-password" /></label>
            <button className="boton-primario w-full" disabled={enviando || !usuario.trim() || !clave}>{enviando ? 'Ingresando…' : 'Ingresar'}</button>
            <p className="text-xs text-koape-gris">¿Primera vez? Pulse «Activar»: le enviamos un PIN a su correo.</p>
          </form>
        ) : (
          <form className="space-y-3 rounded-xl bg-white p-4" onSubmit={(e) => void pedirPin(e)}>
            <p className="text-sm">Escriba su <b>número de documento</b> (C.I., RUC, DNI…) y el <b>correo</b> que tiene registrado en su junta o aguatera. Le enviaremos un <b>PIN</b> para ingresar.</p>
            <label className="block text-sm"><span className="etiqueta">Número de documento</span>
              <input className="campo" inputMode="text" value={documento} onChange={(e) => setDocumento(e.target.value)} /></label>
            <label className="block text-sm"><span className="etiqueta">Correo</span>
              <input type="email" className="campo" value={correo} onChange={(e) => setCorreo(e.target.value)} autoCapitalize="none" /></label>
            <button className="boton-primario w-full" disabled={enviando || !documento.trim() || !correo.trim()}>{enviando ? 'Enviando…' : 'Enviarme el PIN'}</button>
            <p className="text-xs text-koape-gris">Si su correo no está registrado, pídalo en la oficina de su junta: por seguridad solo usamos el correo que ellos tienen cargado.</p>
          </form>
        )}
        <p className="text-center text-xs"><Link className="text-koape-gris hover:underline" to="/ingresar">Ingreso del personal de la institución</Link></p>
      </div>
    </Marco>
  )
}

function ElegirClave({ api }: { api: AxiosInstance }) {
  const navegar = useNavigate()
  const [nueva, setNueva] = useState('')
  const [repetir, setRepetir] = useState('')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)
  if (!leer()) return <Navigate to="/portal" replace />

  async function guardarClave(e: FormEvent) {
    e.preventDefault()
    setError('')
    setEnviando(true)
    try {
      await api.post('portal/cambiar-clave/', { nueva })
      navegar('/portal/cuenta', { replace: true })
    } catch (err) { setError(mensajeDeError(err)) } finally { setEnviando(false) }
  }
  return (
    <Marco>
      <form className="mx-auto max-w-sm space-y-3 rounded-xl bg-white p-4" onSubmit={(e) => void guardarClave(e)}>
        <h1 className="text-xl font-extrabold">Elija su contraseña</h1>
        <p className="text-sm text-koape-gris">El PIN sirve una sola vez. Elija una contraseña de al menos 8 caracteres para las próximas veces.</p>
        <Aviso tipo="error">{error}</Aviso>
        <input type="password" className="campo" placeholder="Contraseña nueva" value={nueva} onChange={(e) => setNueva(e.target.value)} autoComplete="new-password" />
        <input type="password" className="campo" placeholder="Repítala" value={repetir} onChange={(e) => setRepetir(e.target.value)} autoComplete="new-password" />
        {repetir && nueva !== repetir && <p className="text-xs text-koape-rojo">No coinciden.</p>}
        <button className="boton-primario w-full" disabled={enviando || nueva.length < 8 || nueva !== repetir}>Guardar y continuar</button>
      </form>
    </Marco>
  )
}

interface ResumenInstitucion {
  institucion: { codigo: string; nombre: string; telefono: string; direccion: string }
  clientes: { Code: string; nombre: string }[]
  conexiones: number
  saldo_facturas: string
  vencido: string
  a_facturar: string
  deuda_total: string
}

function Encabezado({ api, titulo, volver }: { api: AxiosInstance; titulo: string; volver?: boolean }) {
  const navegar = useNavigate()
  async function salir() {
    try { await api.post('portal/salir/') } catch { /* igual se cierra */ }
    guardar(null)
    navegar('/portal', { replace: true })
  }
  return (
    <div className="mb-4 flex items-start justify-between gap-3">
      <div>{volver && <Link className="text-sm text-koape-rojo" to="/portal/cuenta">← Mis cuentas</Link>}<h1 className="text-2xl font-extrabold">{titulo}</h1></div>
      <button className="boton-secundario" onClick={() => void salir()}>Salir</button>
    </div>
  )
}

function Cuenta({ api }: { api: AxiosInstance }) {
  const [lista, setLista] = useState<ResumenInstitucion[] | null>(null)
  const [nombre, setNombre] = useState('')
  const [error, setError] = useState('')
  const navegar = useNavigate()
  useEffect(() => {
    api.get<{ nombre: string; debe_cambiar_clave: boolean }>('portal/yo/').then((r) => {
      if (r.data.debe_cambiar_clave) navegar('/portal/clave', { replace: true })
      setNombre(r.data.nombre)
      return api.get<ResumenInstitucion[]>('portal/resumen/').then((x) => setLista(x.data))
    }).catch((e) => setError(mensajeDeError(e)))
  }, [api, navegar])
  return (
    <Marco>
      <Encabezado api={api} titulo={`Hola${nombre ? `, ${nombre.split(' ')[0]}` : ''}`} />
      <Aviso tipo="error">{error}</Aviso>
      {lista && lista.length === 0 && <p className="text-sm text-koape-gris">No encontramos cuentas activas a su nombre en las juntas que ofrecen este portal.</p>}
      <div className="grid gap-3 sm:grid-cols-2">
        {lista?.map((x) => (
          <Link key={x.institucion.codigo} to={`/portal/cuenta/${x.institucion.codigo}`} className="block rounded-xl border border-koape-gris-claro bg-white p-4 transition hover:border-koape-magenta">
            <p className="text-lg font-bold">{x.institucion.nombre}</p>
            <p className="text-xs text-koape-gris">{x.conexiones} conexión{x.conexiones === 1 ? '' : 'es'} · {x.institucion.telefono || x.institucion.direccion}</p>
            <p className="mt-3 text-sm">Deuda total</p>
            <p className={`text-2xl font-extrabold ${Number(x.deuda_total) > 0 ? 'text-koape-rojo' : 'text-emerald-700'}`}>{Number(x.deuda_total) > 0 ? gs(x.deuda_total) : 'Al día'}</p>
            {Number(x.vencido) > 0 && <p className="text-xs font-semibold text-koape-rojo">Vencido: {gs(x.vencido)}</p>}
            {Number(x.a_facturar) > 0 && <p className="text-xs text-koape-gris">Incluye {gs(x.a_facturar)} de consumo todavía sin facturar.</p>}
          </Link>
        ))}
      </div>
    </Marco>
  )
}

type Pestania = 'deuda' | 'facturas' | 'pagos' | 'lecturas' | 'conexiones'
const PESTANIAS: [Pestania, string][] = [['deuda', 'Deuda'], ['facturas', 'Facturas'], ['pagos', 'Pagos'], ['lecturas', 'Lecturas'], ['conexiones', 'Conexiones']]

function Institucion({ api }: { api: AxiosInstance }) {
  const { codigo = '' } = useParams()
  const [pestania, setPestania] = useState<Pestania>('deuda')
  // Los datos quedan asociados a su pestaña: al cambiar no se muestran los de la anterior (ni «sin datos» mientras carga).
  const [cargado, setCargado] = useState<{ ruta: string; datos: Record<string, unknown> | unknown[] } | null>(null)
  const [nombre, setNombre] = useState(codigo)
  const [error, setError] = useState('')
  const [foto, setFoto] = useState<string | null>(null)
  const base = `portal/${encodeURIComponent(codigo)}/`
  const datos = cargado?.ruta === `${base}${pestania}/` ? cargado.datos : null

  useEffect(() => {
    api.get<ResumenInstitucion[]>('portal/resumen/').then((r) => setNombre(r.data.find((x) => x.institucion.codigo === codigo)?.institucion.nombre ?? codigo)).catch(() => undefined)
  }, [api, codigo])
  useEffect(() => {
    let vigente = true
    setError('')
    api.get(`${base}${pestania}/`).then((r) => { if (vigente) setCargado({ ruta: `${base}${pestania}/`, datos: r.data }) }).catch((e) => { if (vigente) setError(mensajeDeError(e)) })
    return () => { vigente = false }
  }, [api, base, pestania])

  async function abrir(ruta: string, comoFoto = false) {
    setError('')
    const ventana = comoFoto ? null : window.open('', '_blank')
    try {
      const r = await api.get<Blob>(ruta, { responseType: 'blob' })
      const url = URL.createObjectURL(r.data)
      if (comoFoto) { setFoto(url); return }
      if (ventana) ventana.location.href = url
      else window.location.href = url
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (e) { ventana?.close(); setError(mensajeDeError(e)) }
  }

  const filas = (Array.isArray(datos) ? datos : []) as Record<string, any>[] // eslint-disable-line @typescript-eslint/no-explicit-any
  const deuda = (!Array.isArray(datos) && datos ? datos : null) as Record<string, any> | null // eslint-disable-line @typescript-eslint/no-explicit-any
  return (
    <Marco>
      <Encabezado api={api} titulo={nombre} volver />
      <div className="mb-4 flex gap-1 overflow-x-auto rounded-xl bg-white p-1 text-sm font-semibold">
        {PESTANIAS.map(([p, t]) => <button key={p} className={`whitespace-nowrap rounded-lg px-3 py-2 ${pestania === p ? 'bg-koape-rojo text-white' : ''}`} onClick={() => setPestania(p)}>{t}</button>)}
      </div>
      <Aviso tipo="error">{error}</Aviso>
      {!datos && !error && <p className="text-koape-gris">Cargando…</p>}
      {datos && <div className="rounded-xl bg-white p-4 text-sm">
        {pestania === 'deuda' && deuda && (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <div><p className="etiqueta">Deuda total</p><p className="text-2xl font-extrabold">{gs(deuda.deuda_total)}</p></div>
              <div><p className="etiqueta">Vencido</p><p className={`text-2xl font-extrabold ${Number(deuda.vencido) > 0 ? 'text-koape-rojo' : ''}`}>{gs(deuda.vencido)}</p></div>
              <div><p className="etiqueta">Consumo sin facturar</p><p className="text-2xl font-extrabold">{gs(deuda.a_facturar)}</p></div>
            </div>
            {deuda.facturas.length > 0 && (<div><p className="mb-1 font-bold">Facturas a crédito con saldo</p><ul className="space-y-1">
              {deuda.facturas.map((f: any) => <li key={f.referencia} className="flex justify-between gap-2"><span>Factura {f.numero} · vence {fecha(f.fecha_vencimiento)}{f.estado_cobro === 'vencida' && <b className="text-koape-rojo"> · vencida</b>}</span><b>{gs(f.saldo)}</b></li>)}</ul></div>)}
            {deuda.pendientes_de_facturar.length > 0 && (<div><p className="mb-1 font-bold">Consumos todavía sin facturar</p><ul className="space-y-1">
              {deuda.pendientes_de_facturar.map((q: any, n: number) => <li key={n} className="flex justify-between gap-2"><span>{q.periodo} · {q.conexion} · {num(q.consumo)} m³</span><b>{gs(q.total)}</b></li>)}</ul>
              <p className="mt-1 text-xs text-koape-gris">Se facturan cuando paga en la oficina.</p></div>)}
            {Number(deuda.deuda_total) === 0 && <p className="text-emerald-700">Está al día. ¡Gracias!</p>}
          </div>
        )}
        {pestania === 'facturas' && (
          <ul className="divide-y divide-koape-gris-claro/60">
            {filas.map((f) => (
              <li key={f.referencia} className={`flex flex-wrap items-center justify-between gap-2 py-2 ${f.anulada ? 'text-koape-gris line-through' : ''}`}>
                <span>Factura <b>{f.numero}</b> · {fecha(f.fecha_emision)} · {f.condicion}{f.estado_cobro ? ` · ${({ pagada: 'pagada', parcial: 'pago parcial', pendiente: 'impaga', vencida: 'vencida' } as Record<string, string>)[f.estado_cobro]}` : ''}</span>
                <span className="flex items-center gap-3"><b>{gs(f.total)}</b>{f.pdf && !f.anulada && <button className="text-koape-rojo hover:underline" onClick={() => void abrir(`${base}facturas/${f.referencia}/pdf/`)}>PDF</button>}</span>
              </li>
            ))}
            {filas.length === 0 && <li className="py-2 text-koape-gris">Todavía no tiene facturas.</li>}
          </ul>
        )}
        {pestania === 'pagos' && (
          <ul className="divide-y divide-koape-gris-claro/60">
            {filas.map((p, n) => (
              <li key={n} className={`flex flex-wrap items-center justify-between gap-2 py-2 ${p.revertido ? 'text-koape-gris line-through' : ''}`}>
                <span>{fechaHora(p.fecha_hora)} · {p.origen} · {p.forma_pago}{p.facturas.length ? ` · factura ${p.facturas.join(', ')}` : ''}</span>
                <span className="flex items-center gap-3"><b>{gs(p.importe)}</b>{p.recibo && !p.revertido && <button className="text-koape-rojo hover:underline" onClick={() => void abrir(`${base}recibos/${Number(p.recibo)}/pdf/`)}>Recibo</button>}</span>
              </li>
            ))}
            {filas.length === 0 && <li className="py-2 text-koape-gris">Todavía no tiene pagos registrados.</li>}
          </ul>
        )}
        {pestania === 'lecturas' && (
          <div className="overflow-x-auto"><table className="tabla"><thead><tr><th>Período</th><th>Conexión</th><th className="text-right">Anterior</th><th className="text-right">Actual</th><th className="text-right">Consumo</th><th /></tr></thead>
            <tbody>{filas.map((l) => (
              <tr key={l.comprobante}><td>{l.periodo}</td><td>{l.conexion}</td><td className="text-right">{num(l.lectura_anterior)}</td><td className="text-right">{num(l.lectura_actual)}</td><td className="text-right font-bold">{num(l.consumo)} m³</td>
                <td>{l.foto && <button className="text-koape-rojo hover:underline" onClick={() => void abrir(`${base}lecturas/${l.comprobante}/foto/`, true)}>Foto</button>}</td></tr>))}
              {filas.length === 0 && <tr><td colSpan={6} className="text-center text-koape-gris">Sin lecturas todavía.</td></tr>}</tbody></table></div>
        )}
        {pestania === 'conexiones' && (
          <ul className="space-y-3">
            {filas.map((c) => (
              <li key={c.Code} className="rounded-lg border border-koape-gris-claro p-3">
                <p className="font-bold">{c.direccion || c.Code} <span className="text-xs font-normal text-koape-gris">· {c.Code}</span></p>
                <p className="text-xs text-koape-gris">{c.barrio} · {c.estado} · tarifa {c.tarifa || '—'} · medidor {c.medidor ? (c.medidor_numero ? `N.º ${c.medidor_numero}` : c.medidor) : 'sin medidor'}</p>
                {c.ultima_lectura && <p className="mt-1">Última lectura ({c.ultima_lectura.periodo}): {num(c.ultima_lectura.lectura)} · consumo {num(c.ultima_lectura.consumo)} m³</p>}
              </li>
            ))}
          </ul>
        )}
      </div>}
      {foto && <Modal titulo="Foto del medidor" alCerrar={() => { URL.revokeObjectURL(foto); setFoto(null) }}><img src={foto} alt="Foto del medidor" className="max-h-[70vh] w-full object-contain" /></Modal>}
    </Marco>
  )
}
