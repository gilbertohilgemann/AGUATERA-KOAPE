import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useNavigate, useParams } from 'react-router-dom'
import { mensajeDeError } from '../api/cliente'
import type { ConexionPaquete, PaqueteRecorrido, Recorrido } from '../api/tipos'
import { L, elemento, useMapa } from '../mapa/leaflet'
import { coincide, identificacionMedidor, nombreMedidor } from './medidor'
import { Aviso } from '../componentes/Aviso'
import { Logo } from '../componentes/Logo'
import { useSesion } from '../sesion/ContextoSesion'
import { fechaHora } from '../utilidades/fechas'
import { borrarOperacion, borrarPaquete, guardarOperacion, guardarPaquete, leerPaquete, paquetesDe, pendientes, type Operacion } from './almacenLocal'
import { useCobrador } from './ContextoCobrador'
import { abrirTicket, anchoTicket, guardarAnchoTicket } from './ticket'

const ESTADO_OP: Record<Operacion['estado'], { texto: string; clase: string }> = {
  pendiente: { texto: 'Pendiente de envío', clase: 'bg-amber-100 text-amber-800' },
  sincronizando: { texto: 'Enviando…', clase: 'bg-sky-100 text-sky-800' },
  sincronizada: { texto: 'Enviada', clase: 'bg-emerald-100 text-emerald-800' },
  revision: { texto: 'Enviada · en revisión', clase: 'bg-amber-100 text-amber-800' },
  error: { texto: 'Rechazada', clase: 'bg-rose-100 text-rose-800' },
}

export function InsigniaOperacion({ op }: { op: Operacion }) {
  const e = ESTADO_OP[op.estado]
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${e.clase}`}>{e.texto}</span>
}

/** Marco de la aplicación del cobrador: pensado para el celular, una mano, letra grande. */
export function MarcoCobrador() {
  const { datos, salir, sinConexion } = useSesion()
  const { enLinea, cantidadPendientes, sincronizando, sincronizarAhora, operaciones } = useCobrador()
  const sinEnviar = operaciones.filter((o) => o.estado === 'pendiente' || o.estado === 'sincronizando').length
  const [confirmarSalida, setConfirmarSalida] = useState(false)

  return (
    <div className="mx-auto flex min-h-screen max-w-xl flex-col bg-koape-fondo">
      <header className="sticky top-0 z-[1100] bg-koape-tinta px-4 py-3 text-white shadow">
        <div className="flex items-center justify-between gap-2">
          <Link to="/cobrador" className="flex items-center gap-2"><Logo claro compacto /></Link>
          <div className="flex items-center gap-2 text-xs">
            <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 font-semibold ${enLinea && !sinConexion ? 'bg-emerald-600' : 'bg-slate-600'}`}>
              <span className="h-2 w-2 rounded-full bg-white" />{enLinea && !sinConexion ? 'En línea' : 'Sin conexión'}
            </span>
            <button className="rounded-full bg-white/10 px-2 py-1 font-semibold" onClick={() => setConfirmarSalida(true)}>Salir</button>
          </div>
        </div>
        <p className="mt-1 truncate text-xs text-koape-gris-claro">{datos.usuario.nombre || datos.usuario.usuario} · {datos.institucion.nombre}</p>
      </header>
      <nav className="grid grid-cols-2 border-b border-koape-gris-claro bg-white text-center text-sm font-semibold">
        <NavLink end to="/cobrador" className={({ isActive }) => `py-3 ${isActive ? 'border-b-2 border-koape-rojo text-koape-rojo' : 'text-koape-gris'}`}>Recorridos</NavLink>
        <NavLink to="/cobrador/enviadas" className={({ isActive }) => `py-3 ${isActive ? 'border-b-2 border-koape-rojo text-koape-rojo' : 'text-koape-gris'}`}>
          Lecturas {cantidadPendientes > 0 && <span className="ml-1 rounded-full bg-koape-rojo px-2 text-xs text-white">{cantidadPendientes}</span>}
        </NavLink>
      </nav>
      {cantidadPendientes > 0 && (
        <div className="flex items-center justify-between gap-2 bg-amber-50 px-4 py-2 text-sm text-amber-900">
          <span>{cantidadPendientes} lectura(s) guardadas en el teléfono sin enviar.</span>
          <button className="font-semibold underline disabled:opacity-50" disabled={sincronizando || !enLinea} onClick={() => void sincronizarAhora()}>
            {sincronizando ? 'Enviando…' : 'Enviar ahora'}
          </button>
        </div>
      )}
      <main className="flex-1 p-4"><Outlet /></main>
      {confirmarSalida && (
        <div className="fixed inset-0 z-[1200] grid place-items-center bg-black/40 p-4" role="dialog">
          <div className="w-full max-w-sm rounded-xl bg-white p-5">
            <p className="font-bold">¿Salir de la aplicación?</p>
            <p className="mt-2 text-sm text-koape-gris">
              {sinEnviar > 0
                ? `Hay ${sinEnviar} lectura(s) sin enviar: quedan guardadas en este teléfono y se enviarán cuando usted vuelva a ingresar con conexión.`
                : 'Se borran de este teléfono los datos de los recorridos descargados.'}
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button className="boton-secundario" onClick={() => setConfirmarSalida(false)}>Cancelar</button>
              <button className="boton-primario" onClick={() => void salirLimpiando(datos.institucion.codigo, datos.usuario.usuario, salir)}>Salir</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

async function salirLimpiando(institucion: string, nombre: string, salir: () => Promise<void>) {
  const usuario = `${institucion}/${nombre}`
  try {
    for (const p of await paquetesDe(usuario)) await borrarPaquete(usuario, p.code)
  } catch {
    /* sin IndexedDB */
  }
  await salir()
}

function Tarjeta({ children }: { children: ReactNode }) {
  return <div className="rounded-xl border border-koape-gris-claro bg-white p-4 shadow-sm">{children}</div>
}

/** Recorridos asignados: del servidor si hay conexión; si no, los descargados en el teléfono. */
export function InicioCobrador() {
  const { api, sinConexion } = useSesion()
  const { usuario, enLinea, operaciones } = useCobrador()
  const [lista, setLista] = useState<{ recorrido: Recorrido; descargado_en: string | null }[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let vigente = true
    async function cargar() {
      const locales = await paquetesDe(usuario).catch(() => [])
      const porCode = new Map(locales.map((p) => [p.code, p]))
      if (enLinea && !sinConexion) {
        try {
          const r = await api.get<Recorrido[]>('cobrador/recorridos/')
          if (vigente) setLista(r.data.map((rec) => ({ recorrido: rec, descargado_en: porCode.get(rec.Code)?.descargado_en ?? null })))
          return
        } catch (e) {
          if (vigente) setError(mensajeDeError(e))
        }
      }
      if (vigente) setLista(locales.map((p) => ({ recorrido: p.paquete.recorrido, descargado_en: p.descargado_en })))
    }
    void cargar()
    return () => { vigente = false }
  }, [api, usuario, enLinea, sinConexion])

  if (!lista) return <p className="text-koape-gris">Cargando…</p>
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-extrabold">Mis recorridos</h1>
      <Aviso tipo="error">{error}</Aviso>
      {lista.length === 0 && <p className="text-sm text-koape-gris">{enLinea ? 'No tiene recorridos abiertos asignados.' : 'Sin conexión y sin recorridos descargados en este teléfono.'}</p>}
      {lista.map(({ recorrido: r, descargado_en }) => {
        const locales = operaciones.filter((o) => o.recorrido === r.Code && o.estado !== 'error').length
        return (
          <Link key={r.Code} to={`/cobrador/r/${r.Code}`} className="block">
            <Tarjeta>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-lg font-bold">{r.nombre}</p>
                  <p className="text-xs text-koape-gris">{r.Code} · {r.periodo}</p>
                </div>
                <span className="text-2xl text-koape-rojo">›</span>
              </div>
              <p className="mt-2 text-sm">{r.avance.leidas} de {r.avance.total} leídas{locales ? ` · ${locales} en este teléfono` : ''}</p>
              <p className="text-xs text-koape-gris">{descargado_en ? `Descargado ${fechaHora(descargado_en)}` : 'No descargado en este teléfono'}</p>
            </Tarjeta>
          </Link>
        )
      })}
    </div>
  )
}

/** Un recorrido: avance, conexiones en orden de visita y el botón para tomar lecturas. */
export function RecorridoCobrador() {
  const { code = '' } = useParams()
  const { api, sinConexion } = useSesion()
  const { usuario, enLinea, operaciones } = useCobrador()
  const navegar = useNavigate()
  const [paquete, setPaquete] = useState<PaqueteRecorrido | null>(null)
  const [descargado, setDescargado] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [buscar, setBuscar] = useState('')
  const [vista, setVista] = useState<'lista' | 'mapa'>('lista')
  const enRed = enLinea && !sinConexion

  const descargar = useCallback(async () => {
    const r = await api.get<PaqueteRecorrido>(`cobrador/recorridos/${encodeURIComponent(code)}/paquete/`)
    await guardarPaquete(usuario, r.data)
    setPaquete(r.data)
    setDescargado(new Date().toISOString())
  }, [api, code, usuario])

  useEffect(() => {
    let vigente = true
    leerPaquete(usuario, code).then((local) => {
      if (vigente && local) { setPaquete(local.paquete); setDescargado(local.descargado_en) }
    }).catch(() => undefined)
    if (enRed) descargar().catch((e) => vigente && setError(mensajeDeError(e)))
    return () => { vigente = false }
  }, [usuario, code, enRed, descargar])

  async function postear(sub: 'iniciar' | 'finalizar') {
    setError('')
    setAviso('')
    try {
      await api.post(`cobrador/recorridos/${encodeURIComponent(code)}/${sub}/`)
      if (sub === 'finalizar') {
        const sinEnviar = pendientes(operaciones).filter((o) => o.recorrido === code).length
        if (!sinEnviar) await borrarPaquete(usuario, code)
        navegar('/cobrador')
      } else {
        setAviso('Recorrido iniciado. ¡Buen trabajo!')
        await descargar()
      }
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }

  if (!paquete) return error ? <Aviso tipo="error">{error}</Aviso> : <p className="text-koape-gris">{enRed ? 'Descargando el recorrido…' : 'Este recorrido no está descargado en el teléfono. Conéctese para descargarlo.'}</p>
  const locales = new Map(operaciones.filter((o) => o.recorrido === code && o.estado !== 'error').map((o) => [o.conexion, o]))
  const leidas = paquete.conexiones.filter((c) => c.leida || locales.has(c.conexion)).length
  // Búsqueda dentro del recorrido por número de orden o número del medidor (no abre el padrón).
  const texto = buscar.trim()
  const visibles = texto ? paquete.conexiones.filter((c) => coincide(c, texto)) : paquete.conexiones
  const yo = paquete.recorrido.cobradores.find((c) => c.activa && c.usuario === usuario.split('/')[1])

  return (
    <div className="space-y-3">
      <div>
        <p className="text-sm"><Link className="text-koape-rojo" to="/cobrador">← Mis recorridos</Link></p>
        <h1 className="text-xl font-extrabold">{paquete.recorrido.nombre}</h1>
        <p className="text-xs text-koape-gris">{paquete.recorrido.Code} · {paquete.recorrido.periodo} · descargado {fechaHora(descargado)}</p>
      </div>
      <Aviso tipo="error">{error}</Aviso>
      <Aviso tipo="exito">{aviso}</Aviso>
      <Tarjeta>
        <div className="flex h-3 overflow-hidden rounded-full bg-koape-fondo">
          <div className="bg-emerald-500" style={{ width: `${paquete.conexiones.length ? (leidas / paquete.conexiones.length) * 100 : 0}%` }} />
        </div>
        <p className="mt-2 text-sm font-semibold">{leidas} de {paquete.conexiones.length} leídas</p>
      </Tarjeta>
      <Link to={`/cobrador/r/${code}/leer`} className="boton-primario block w-full py-4 text-center text-lg">📷 Tomar lectura</Link>
      {enRed && !yo?.iniciado_en && <button className="boton-secundario w-full" onClick={() => void postear('iniciar')}>Iniciar recorrido</button>}
      <div className="flex gap-2">
        <input className="campo flex-1" type="search" inputMode="text" placeholder="🔎 N.º de orden o número de medidor" value={buscar} onChange={(e) => setBuscar(e.target.value)} />
        <div className="flex rounded-lg border border-koape-gris-claro bg-white p-0.5 text-sm font-semibold">
          <button className={`rounded-md px-3 ${vista === 'lista' ? 'bg-koape-tinta text-white' : ''}`} onClick={() => setVista('lista')}>Lista</button>
          <button className={`rounded-md px-3 ${vista === 'mapa' ? 'bg-koape-tinta text-white' : ''}`} onClick={() => setVista('mapa')}>Mapa</button>
        </div>
      </div>
      {vista === 'mapa' ? (
        <MapaRecorrido conexiones={visibles} leidas={new Set(paquete.conexiones.filter((c) => c.leida || locales.has(c.conexion)).map((c) => c.conexion))}
          alLeer={(m) => navegar(`/cobrador/r/${code}/leer?medidor=${encodeURIComponent(m)}`)} />
      ) : (
        <div className="rounded-xl border border-koape-gris-claro bg-white">
          <p className="border-b border-koape-gris-claro px-4 py-2 text-xs font-semibold text-koape-gris uppercase">Orden de visita{texto ? ` · ${visibles.length} encontrada${visibles.length === 1 ? '' : 's'}` : ''}</p>
          <ul className="divide-y divide-koape-gris-claro/60">
            {visibles.map((c) => {
              const local = locales.get(c.conexion)
              const hecha = !!(local || c.leida)
              return (
                <li key={c.conexion} className="flex items-center justify-between gap-2 px-4 py-3 text-sm">
                  <span>
                    <b className="mr-2 text-koape-gris">{c.orden}</b>{c.direccion || 'Sin dirección'}{c.barrio ? <span className="text-xs text-koape-gris"> · {c.barrio}</span> : null}
                    {c.medidor && <span className="block pl-5 text-xs text-koape-gris">Medidor {nombreMedidor(c)}</span>}
                  </span>
                  <span className="flex shrink-0 flex-col items-end gap-1">
                    {local ? <InsigniaOperacion op={local} /> : c.leida ? <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">Leída</span>
                      : !c.medidor ? <span className="text-xs text-koape-rojo">Sin medidor</span> : <span className="text-xs text-koape-gris">Pendiente</span>}
                    {!hecha && c.medidor && <Link className="text-xs font-semibold text-koape-rojo" to={`/cobrador/r/${code}/leer?medidor=${encodeURIComponent(identificacionMedidor(c))}`}>Leer este medidor ›</Link>}
                  </span>
                </li>
              )
            })}
            {visibles.length === 0 && <li className="px-4 py-3 text-sm text-koape-gris">Ningún orden ni número de medidor del recorrido coincide con «{buscar}».</li>}
          </ul>
        </div>
      )}
      {enRed && yo?.iniciado_en && (
        <button className="boton-secundario w-full" onClick={() => { if (window.confirm('¿Finalizar el recorrido? Podrá retomarlo mientras siga abierto.')) void postear('finalizar') }}>
          Finalizar recorrido
        </button>
      )}
      <p className="text-xs text-koape-gris">Los datos del titular y la lectura anterior se ven recién después de fotografiar el medidor.</p>
    </div>
  )
}

/** Lecturas tomadas en este teléfono: estado de envío, errores y comprobantes. */
export function LecturasCobrador() {
  const { api } = useSesion()
  const { operaciones, recargar, sincronizarAhora, enLinea, sincronizando } = useCobrador()
  const [error, setError] = useState('')

  async function reintentar(op: Operacion) {
    await guardarOperacion({ ...op, estado: 'pendiente', error: undefined })
    await recargar()
    await sincronizarAhora()
  }

  async function descartar(op: Operacion) {
    if (!window.confirm(`¿Descartar la lectura ${op.lectura_actual} del medidor ${op.medidor}? Se borra de este teléfono y no se envía.`)) return
    await borrarOperacion(op.id_operacion)
    await recargar()
  }

  const [ancho, setAncho] = useState(anchoTicket())

  async function ticket(op: Operacion) {
    setError('')
    if (op.comprobante) setError(await abrirTicket(api, op.comprobante))
  }

  const lista = [...operaciones].reverse()
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-extrabold">Lecturas de este teléfono</h1>
        <button className="boton-secundario" disabled={!enLinea || sincronizando} onClick={() => void sincronizarAhora()}>{sincronizando ? 'Enviando…' : 'Enviar'}</button>
      </div>
      <Aviso tipo="error">{error}</Aviso>
      {lista.length === 0 && <p className="text-sm text-koape-gris">Todavía no tomó lecturas en este teléfono.</p>}
      {lista.map((op) => (
        <Tarjeta key={op.id_operacion}>
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="font-bold">Medidor {op.medidor} · {op.lectura_actual}</p>
              <p className="text-xs text-koape-gris">Conexión {op.conexion} · {fechaHora(op.capturada_en)}</p>
            </div>
            <InsigniaOperacion op={op} />
          </div>
          {op.comprobante && <p className="mt-2 text-sm">Comprobante <b>{op.comprobante}</b>{op.consumo ? ` · consumo ${Number(op.consumo).toLocaleString('es-PY', { maximumFractionDigits: 3 })}` : ''}{op.estado === 'revision' && op.motivo_revision ? ` · ${op.motivo_revision}` : ''}</p>}
          {op.error && <p className="mt-2 text-sm text-rose-700">{op.error}</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            {op.comprobante && enLinea && <button className="boton-secundario" onClick={() => void ticket(op)}>🧾 Ticket</button>}
            {op.estado === 'error' && <button className="boton-secundario" onClick={() => void reintentar(op)}>Reintentar</button>}
            {op.estado === 'error' && <button className="boton-secundario" onClick={() => void descartar(op)}>Descartar</button>}
          </div>
        </Tarjeta>
      ))}
      <div className="flex items-center justify-between gap-2 text-xs text-koape-gris">
        <span>Papel de la impresora del ticket</span>
        <span className="flex rounded-lg border border-koape-gris-claro bg-white p-0.5 font-semibold">
          {(['58', '80'] as const).map((a) => (
            <button key={a} className={`rounded-md px-2 py-0.5 ${ancho === a ? 'bg-koape-tinta text-white' : ''}`} onClick={() => { guardarAnchoTicket(a); setAncho(a) }}>{a} mm</button>
          ))}
        </span>
      </div>
      <p className="text-xs text-koape-gris">Las fotos se borran del teléfono cuando el servidor confirma que recibió la lectura. Las enviadas se quitan de esta lista a los 7 días.</p>
    </div>
  )
}

/**
 * Mapa del recorrido: verde = leída (o ya tomada en este teléfono), rojo = falta. Muestra solo dirección y medidor
 * (los datos del titular siguen apareciendo recién después de la foto). Sin internet no hay fondo de calles, pero los
 * puntos y la posición propia se siguen viendo.
 */
function MapaRecorrido({ conexiones, leidas, alLeer }: { conexiones: ConexionPaquete[]; leidas: Set<string>; alLeer: (medidor: string) => void }) {
  const { ref, mapa } = useMapa({ zoom: 16 })
  const encuadrado = useRef(false)
  const yo = useRef<L.CircleMarker | null>(null)
  const alLeerRef = useRef(alLeer)
  alLeerRef.current = alLeer
  const clave = [...leidas].sort().join(',')
  // El mapa se redibuja solo si cambian los puntos o su estado (no en cada actualización de la pantalla: así no se
  // cierra la ventanita abierta).
  const lista = useRef(conexiones)
  lista.current = conexiones
  const claveConexiones = conexiones.map((c) => [c.conexion, c.orden, c.medidor, c.medidor_numero, c.lat, c.lon, c.direccion].join('|')).join(',')
  const sinUbicacion = conexiones.filter((c) => c.lat === null || c.lon === null).length

  useEffect(() => {
    if (!mapa) return
    const hechas = new Set(clave ? clave.split(',') : [])
    const capa = L.featureGroup().addTo(mapa)
    for (const c of lista.current) {
      if (c.lat === null || c.lon === null) continue
      const hecha = hechas.has(c.conexion)
      const punto = L.circleMarker([c.lat, c.lon], { radius: 11, color: '#fff', weight: 2, fillColor: hecha ? '#16A34A' : '#DC2626', fillOpacity: 0.95 })
      const popup = document.createElement('div')
      popup.append(elemento('b', `${c.orden}. ${c.direccion || 'Sin dirección'}`), document.createElement('br'),
        elemento('span', `Medidor ${nombreMedidor(c)} · ${hecha ? 'leída' : 'falta leer'}`))
      if (!hecha && c.medidor) {
        const boton = elemento('button', 'Leer este medidor', 'mt-2 block w-full rounded bg-koape-rojo px-2 py-1 font-semibold text-white')
        const medidor = identificacionMedidor(c)
        boton.addEventListener('click', () => alLeerRef.current(medidor))
        popup.append(boton)
      }
      punto.bindPopup(popup).bindTooltip(String(c.orden), { permanent: true, direction: 'center', className: 'etiqueta-orden' })
      capa.addLayer(punto)
    }
    if (!encuadrado.current && capa.getLayers().length) {
      mapa.fitBounds(capa.getBounds().pad(0.2), { maxZoom: 17 })
      encuadrado.current = true
    }
    return () => { capa.remove() }
  }, [mapa, claveConexiones, clave])

  // Dónde está el cobrador (punto azul), si el teléfono da la ubicación.
  useEffect(() => {
    if (!mapa || !('geolocation' in navigator)) return
    const id = navigator.geolocation.watchPosition((p) => {
      const lugar: L.LatLngTuple = [p.coords.latitude, p.coords.longitude]
      if (yo.current) yo.current.setLatLng(lugar)
      else yo.current = L.circleMarker(lugar, { radius: 7, color: '#fff', weight: 3, fillColor: '#2563EB', fillOpacity: 1 }).bindTooltip('Usted está aquí').addTo(mapa)
    }, () => undefined, { enableHighAccuracy: true, maximumAge: 10_000 })
    return () => { navigator.geolocation.clearWatch(id); yo.current?.remove(); yo.current = null }
  }, [mapa])

  return (
    <div className="space-y-2">
      <div ref={ref} className="h-[60vh] w-full overflow-hidden rounded-xl border border-koape-gris-claro" />
      <p className="flex flex-wrap gap-3 text-xs text-koape-gris">
        <span><span className="mr-1 inline-block h-3 w-3 rounded-full bg-emerald-600 align-middle" />Leída</span>
        <span><span className="mr-1 inline-block h-3 w-3 rounded-full bg-red-600 align-middle" />Falta leer</span>
        <span><span className="mr-1 inline-block h-3 w-3 rounded-full bg-blue-600 align-middle" />Usted</span>
        {sinUbicacion > 0 && <span>{sinUbicacion} sin ubicación en el mapa (ver la lista)</span>}
      </p>
    </div>
  )
}
