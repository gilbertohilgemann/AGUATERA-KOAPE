import axios from 'axios'
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { mensajeDeError } from '../../api/cliente'
import type { EstadoCuenta, FormaPago, Pagina, Pago, Recibo } from '../../api/tipos'
import { Aviso } from '../../componentes/Aviso'
import { Campo } from '../../componentes/Campo'
import { Encabezado } from '../../componentes/Encabezado'
import { Modal } from '../../componentes/Modal'
import { Paginador } from '../../componentes/Paginador'
import { useSesion } from '../../sesion/ContextoSesion'
import { fechaHora } from '../../utilidades/fechas'
import { nuevoIdentificador } from '../../utilidades/identificador'
import { InsigniaCobro } from '../facturacion/Facturas'
import { useAbrirPdf } from '../lecturas/Lecturas'
import { AvisoCajaCerrada } from '../caja/Caja'
import { BuscadorCliente } from '../padron/BuscadorCliente'
import { gs } from '../tarifas/Tarifas'

const fecha = (v: string | null) => (v ? new Date(`${v}T12:00:00`).toLocaleDateString('es-PY') : '—')

/** Guaraníes escritos como en Paraguay: «44.800» → 44800. Vacío o inválido → 0. */
export const guaranies = (v: string) => {
  const n = Number(v.trim().replace(/\./g, '').replace(',', '.'))
  return Number.isFinite(n) ? n : 0
}
const miles = (n: number) => (n ? n.toLocaleString('es-PY', { maximumFractionDigits: 0 }) : '')

/** Primero la factura vencida más antigua (el servidor ya las manda en ese orden). */
function repartir(facturas: EstadoCuenta['facturas'], importe: number): Record<string, string> {
  let resto = importe
  const montos: Record<string, string> = {}
  for (const f of facturas) {
    const parte = Math.min(resto, Number(f.saldo))
    montos[f.referencia] = parte > 0 ? miles(parte) : ''
    resto -= Math.max(parte, 0)
  }
  return montos
}

/** Cobro de facturas a crédito: un pago, repartido entre una o varias facturas, con su recibo. */
export function Cobrar() {
  const { api } = useSesion()
  const navegar = useNavigate()
  const [parametros] = useSearchParams()
  const [codigo, setCodigo] = useState(parametros.get('cliente') ?? '')
  const [cuenta, setCuenta] = useState<EstadoCuenta | null>(null)
  const [importe, setImporte] = useState('')
  const [forma, setForma] = useState('')
  const [referencia, setReferencia] = useState('')
  const [observaciones, setObservaciones] = useState('')
  const [montos, setMontos] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [recarga, setRecarga] = useState(0)
  // Una clave por cobro: si la red se corta y se reintenta, el servidor devuelve el MISMO recibo (no cobra dos veces).
  const clave = useRef(nuevoIdentificador())

  useEffect(() => {
    if (!codigo) return
    let vigente = true
    setCuenta(null)
    api.get<EstadoCuenta>('cobranzas/estado-cuenta/', { params: { cliente: codigo } })
      .then((r) => {
        if (!vigente) return
        setCuenta(r.data)
        setMontos({})
        setImporte('')
        setForma((actual) => (r.data.formas_pago.some((f) => f.Code === actual) ? actual : r.data.formas_pago[0]?.Code ?? ''))
      })
      .catch((e) => { if (vigente) setError(mensajeDeError(e)) })
    return () => { vigente = false }
  }, [api, codigo, recarga])

  const automatico = cuenta?.aplicacion_pagos === 'automatica'
  const total = guaranies(importe)
  const aplicado = Object.values(montos).reduce((s, v) => s + guaranies(v), 0)
  const formaElegida = cuenta?.formas_pago.find((f) => f.Code === forma)
  const excedidas = cuenta?.facturas.filter((f) => guaranies(montos[f.referencia] ?? '') > Number(f.saldo)) ?? []
  const listo = !!cuenta && total > 0 && aplicado === total && !excedidas.length && !!formaElegida
    && (!formaElegida.requiere_referencia || !!referencia.trim()) && total <= Number(cuenta.total_saldo)

  function cambiarImporte(v: string) {
    setImporte(v)
    if (automatico && cuenta) setMontos(repartir(cuenta.facturas, guaranies(v)))
  }

  async function cobrar(e: FormEvent) {
    e.preventDefault()
    if (!cuenta || !listo || enviando) return
    setError('')
    setEnviando(true)
    try {
      const aplicaciones = cuenta.facturas.filter((f) => guaranies(montos[f.referencia] ?? '') > 0)
        .map((f) => ({ factura: f.referencia, importe: String(guaranies(montos[f.referencia])) }))
      const r = await api.post<Recibo>('recibos/', {
        cliente: cuenta.cliente.Code, importe: String(total), forma_pago: forma, referencia_externa: referencia,
        observaciones, clave: clave.current, aplicaciones,
      })
      clave.current = nuevoIdentificador()
      navegar(`/panel/recibos/${r.data.numero}`)
    } catch (err) {
      const estado = axios.isAxiosError(err) ? err.response?.status : undefined
      if (estado !== undefined && estado >= 400 && estado < 500) {
        // Rechazo definitivo (ej. otro cajero cobró antes): clave nueva y saldos actualizados.
        setError(mensajeDeError(err))
        clave.current = nuevoIdentificador()
        setRecarga((n) => n + 1)
      } else {
        // Corte o error del servidor: no se sabe si se registró. Se conserva la MISMA clave y lo cargado:
        // al volver a pulsar, el servidor devuelve el recibo ya emitido en lugar de cobrar dos veces.
        setError(`${mensajeDeError(err)} No se sabe si el cobro quedó registrado: vuelva a pulsar «Cobrar y emitir recibo» sin cambiar nada (no se duplica).`)
      }
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="max-w-4xl">
      <Encabezado titulo="Cobrar facturas a crédito" descripcion="Registre el pago del cliente, repártalo entre sus facturas a crédito y emita el recibo. Se admiten pagos parciales." />
      <Aviso tipo="error">{error}</Aviso>
      <AvisoCajaCerrada />
      <form className="tarjeta space-y-4 p-5" onSubmit={(e) => void cobrar(e)}>
        <Campo etiqueta="Cliente (titular)">
          <BuscadorCliente valor={cuenta ? { Code: cuenta.cliente.Code, nombre: cuenta.cliente.nombre } : null}
            alElegir={(c) => { setError(''); clave.current = nuevoIdentificador(); setCodigo(c.Code) }} />
        </Campo>
        {cuenta && cuenta.facturas.length === 0 && <p className="text-sm text-koape-gris">El cliente no tiene facturas a crédito con saldo pendiente.</p>}
        {cuenta && cuenta.facturas.length > 0 && (
          <>
            <div className="grid gap-4 sm:grid-cols-3">
              <Campo etiqueta="Importe recibido (Gs.)">
                <input className="campo text-lg font-bold" inputMode="numeric" placeholder="0" value={importe} onChange={(e) => cambiarImporte(e.target.value)} />
              </Campo>
              <Campo etiqueta="Forma de pago">
                <select className="campo" value={forma} onChange={(e) => setForma(e.target.value)}>
                  {cuenta.formas_pago.map((f) => <option key={f.Code} value={f.Code}>{f.nombre}</option>)}
                </select>
              </Campo>
              {formaElegida?.requiere_referencia
                ? <Campo etiqueta="Referencia de la operación"><input className="campo" placeholder="N° de transferencia o voucher" value={referencia} onChange={(e) => setReferencia(e.target.value)} /></Campo>
                : <Campo etiqueta="Observaciones"><input className="campo" value={observaciones} onChange={(e) => setObservaciones(e.target.value)} /></Campo>}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm">Deuda a crédito: <b>{gs(cuenta.total_saldo)}</b> · reparto {automatico ? 'automático (la vencida más antigua primero)' : 'manual'}</p>
              <button type="button" className="boton-secundario" disabled={!total} onClick={() => setMontos(repartir(cuenta.facturas, total))}>Repartir: la más antigua primero</button>
            </div>
            <div className="overflow-x-auto">
              <table className="tabla">
                <thead><tr><th>Factura</th><th>Emisión</th><th>Vence</th><th className="text-right">Total</th><th className="text-right">Saldo</th><th className="text-right">Aplicar</th><th className="text-right">Queda</th></tr></thead>
                <tbody>
                  {cuenta.facturas.map((f) => {
                    const parte = guaranies(montos[f.referencia] ?? '')
                    const excede = parte > Number(f.saldo)
                    return (
                      <tr key={f.referencia}>
                        <td><Link className="text-koape-rojo hover:underline" to={`/panel/facturas/${f.referencia}`}>{f.numero}</Link> <InsigniaCobro estado={f.estado_cobro} /></td>
                        <td>{fecha(f.fecha_emision)}</td>
                        <td>{fecha(f.fecha_vencimiento)}</td>
                        <td className="text-right">{gs(f.total)}</td>
                        <td className="text-right font-semibold">{gs(f.saldo)}</td>
                        <td className="text-right">
                          <input className={`campo w-32 text-right ${excede ? 'border-koape-rojo' : ''}`} inputMode="numeric" aria-label={`Aplicar a ${f.numero}`}
                            value={montos[f.referencia] ?? ''} onChange={(e) => setMontos({ ...montos, [f.referencia]: e.target.value })} />
                        </td>
                        <td className="text-right">{gs(Math.max(Number(f.saldo) - parte, 0))}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {excedidas.length > 0 && <Aviso tipo="error">A {excedidas.map((f) => f.numero).join(', ')} se le aplica más que su saldo.</Aviso>}
            {total > Number(cuenta.total_saldo) && <Aviso tipo="error">El importe supera la deuda: no se admite saldo a favor, el vuelto se entrega en el momento.</Aviso>}
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-koape-gris-claro pt-4">
              <p>Recibido <b className="text-xl">{gs(total)}</b> · aplicado <b className={aplicado === total ? 'text-emerald-700' : 'text-koape-rojo'}>{gs(aplicado)}</b>
                {aplicado !== total && total > 0 && <span className="text-sm text-koape-rojo"> (debe ser igual al importe)</span>}</p>
              <button className="boton-primario" disabled={!listo || enviando}>{enviando ? 'Registrando…' : 'Cobrar y emitir recibo'}</button>
            </div>
          </>
        )}
      </form>
    </div>
  )
}

export function Recibos() {
  const { api, puede } = useSesion()
  const [filtros, setFiltros] = useState({ buscar: '', estado: '', desde: '', hasta: '' })
  const [pagina, setPagina] = useState(1)
  const [datos, setDatos] = useState<Pagina<Recibo> | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const t = setTimeout(() => {
      const params = Object.fromEntries(Object.entries({ ...filtros, pagina }).filter(([, v]) => v !== ''))
      api.get<Pagina<Recibo>>('recibos/', { params }).then((r) => { setDatos(r.data); setError('') }).catch((e) => setError(mensajeDeError(e)))
    }, 250)
    return () => clearTimeout(t)
  }, [api, filtros, pagina])
  const filtrar = (c: Partial<typeof filtros>) => { setPagina(1); setFiltros({ ...filtros, ...c }) }

  return (
    <div>
      <Encabezado titulo="Recibos" descripcion="Recibos de cobro de facturas a crédito."
        acciones={puede('cobranzas.registrar') && <Link className="boton-primario" to="/panel/cobrar">Cobrar</Link>} />
      <Aviso tipo="error">{error}</Aviso>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Campo etiqueta="Buscar"><input className="campo" placeholder="Número, cliente, RUC" value={filtros.buscar} onChange={(e) => filtrar({ buscar: e.target.value })} /></Campo>
        <Campo etiqueta="Estado">
          <select className="campo" value={filtros.estado} onChange={(e) => filtrar({ estado: e.target.value })}>
            <option value="">Todos</option><option value="emitido">Emitidos</option><option value="anulado">Anulados</option>
          </select>
        </Campo>
        <Campo etiqueta="Desde"><input type="date" className="campo" value={filtros.desde} onChange={(e) => filtrar({ desde: e.target.value })} /></Campo>
        <Campo etiqueta="Hasta"><input type="date" className="campo" value={filtros.hasta} onChange={(e) => filtrar({ hasta: e.target.value })} /></Campo>
      </div>
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Número</th><th>Fecha</th><th>Cliente</th><th>Forma de pago</th><th>Facturas</th><th className="text-right">Importe</th><th>Estado</th></tr></thead>
          <tbody>
            {datos?.results.map((r) => (
              <tr key={r.numero} className={r.estado === 'anulado' ? 'text-koape-gris' : ''}>
                <td><Link className="font-semibold text-koape-rojo hover:underline" to={`/panel/recibos/${r.numero}`}>{r.numero}</Link></td>
                <td>{fechaHora(r.fecha_hora)}</td>
                <td>{r.cliente_nombre}</td>
                <td>{r.forma_pago}</td>
                <td className="text-xs">{r.aplicaciones.map((a) => a.numero).join(', ')}</td>
                <td className="text-right font-semibold">{gs(r.importe)}</td>
                <td>{r.estado_nombre}</td>
              </tr>
            ))}
            {datos?.results.length === 0 && <tr><td colSpan={7} className="text-center text-koape-gris">Sin recibos.</td></tr>}
          </tbody>
        </table>
      </div>
      {datos && <Paginador pagina={pagina} total={datos.count} alCambiar={setPagina} />}
    </div>
  )
}

export function FichaRecibo() {
  const { numero = '' } = useParams()
  const { api, puede } = useSesion()
  const abrirPdf = useAbrirPdf()
  const [r, setR] = useState<Recibo | null>(null)
  const [error, setError] = useState('')
  const [exito, setExito] = useState('')
  const [anulando, setAnulando] = useState(false)
  const [motivo, setMotivo] = useState('')
  const [procesando, setProcesando] = useState(false)
  const ruta = `recibos/${encodeURIComponent(numero)}/`

  const cargar = useCallback(() => {
    api.get<Recibo>(ruta).then((x) => setR(x.data)).catch((e) => setError(mensajeDeError(e)))
  }, [api, ruta])
  useEffect(cargar, [cargar])

  async function anular(e: FormEvent) {
    e.preventDefault()
    if (procesando) return
    setProcesando(true)
    setError('')
    try {
      setR((await api.post<Recibo>(`${ruta}anular/`, { motivo })).data)
      setExito('Recibo anulado: el pago quedó revertido y las facturas recuperaron su saldo.')
      setAnulando(false)
    } catch (err) {
      setError(mensajeDeError(err))
    } finally {
      setProcesando(false)
    }
  }

  if (!r) return error ? <Aviso tipo="error">{error}</Aviso> : <p className="text-koape-gris">Cargando…</p>
  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm"><Link className="text-koape-rojo hover:underline" to="/panel/recibos">← Recibos</Link></p>
          <h1 className="text-2xl font-extrabold">Recibo {r.numero}</h1>
          <p className="text-sm text-koape-gris">{fechaHora(r.fecha_hora)} · cobrado por {r.cobrado_por} · {r.estado_nombre}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="boton-primario" onClick={() => void abrirPdf(`${ruta}pdf/`)}>Imprimir (PDF)</button>
          {r.estado === 'emitido' && puede('cobranzas.anular') && <button className="boton-secundario" onClick={() => setAnulando(true)}>Anular</button>}
        </div>
      </div>
      <Aviso tipo="error">{error}</Aviso>
      <Aviso tipo="exito">{exito}</Aviso>
      {r.estado === 'anulado' && <Aviso tipo="error">Anulado {fechaHora(r.anulado_en)} por {r.anulado_por}: {r.motivo_anulacion}. El pago quedó revertido.</Aviso>}
      <section className="tarjeta p-5">
        <dl className="grid gap-3 text-sm sm:grid-cols-3">
          <div><dt className="etiqueta">Cliente</dt><dd className="font-semibold">{r.cliente_nombre}</dd><dd className="text-xs text-koape-gris">{r.cliente} · RUC/C.I. {r.cliente_documento || '—'}</dd></div>
          <div><dt className="etiqueta">Importe</dt><dd className="text-xl font-extrabold">{gs(r.importe)}</dd></div>
          <div><dt className="etiqueta">Forma de pago</dt><dd>{r.forma_pago}{r.referencia_externa ? ` · ${r.referencia_externa}` : ''}</dd></div>
        </dl>
        {r.observaciones && <p className="mt-3 text-sm">Observaciones: {r.observaciones}</p>}
      </section>
      <section className="tarjeta overflow-x-auto p-5">
        <table className="tabla">
          <thead><tr><th>Factura</th><th>Vence</th><th className="text-right">Saldo anterior</th><th className="text-right">Aplicado</th><th className="text-right">Saldo</th></tr></thead>
          <tbody>
            {r.aplicaciones.map((a) => (
              <tr key={a.factura} className={a.estado !== 'vigente' ? 'text-koape-gris line-through' : ''}>
                <td><Link className="text-koape-rojo hover:underline" to={`/panel/facturas/${a.factura}`}>{a.numero}</Link></td>
                <td>{fecha(a.fecha_vencimiento)}</td>
                <td className="text-right">{gs(a.saldo_anterior)}</td>
                <td className="text-right font-semibold">{gs(a.importe)}</td>
                <td className="text-right">{gs(a.saldo_posterior)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-3 text-sm">Saldo pendiente del cliente después de este cobro: <b>{gs(r.saldo_restante)}</b></p>
      </section>
      {anulando && (
        <Modal titulo="Anular recibo" alCerrar={() => setAnulando(false)}>
          <form className="space-y-4" onSubmit={(e) => void anular(e)}>
            <p className="text-sm">El recibo queda anulado con su número, el pago queda revertido (no se borra) y las facturas vuelven a tener su saldo.</p>
            <Campo etiqueta="Motivo (obligatorio)"><textarea className="campo" value={motivo} onChange={(e) => setMotivo(e.target.value)} /></Campo>
            <div className="flex justify-end gap-2">
              <button type="button" className="boton-secundario" onClick={() => setAnulando(false)}>Cancelar</button>
              <button className="boton-primario" disabled={!motivo.trim() || procesando}>Anular</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}

/** Historial de cobranzas: todos los pagos (contado y recibos), con su trazabilidad. */
export function HistorialCobros() {
  const { api } = useSesion()
  const hoy = new Date().toLocaleDateString('en-CA')
  const [filtros, setFiltros] = useState({ cliente: '', origen: '', estado: '', forma_pago: '', desde: hoy, hasta: hoy })
  const [pagina, setPagina] = useState(1)
  const [datos, setDatos] = useState<Pagina<Pago> | null>(null)
  const [formas, setFormas] = useState<FormaPago[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    api.get<FormaPago[]>('formas-pago/').then((r) => setFormas(r.data)).catch(() => setFormas([]))
  }, [api])
  useEffect(() => {
    const t = setTimeout(() => {
      const params = Object.fromEntries(Object.entries({ ...filtros, pagina }).filter(([, v]) => v !== ''))
      api.get<Pagina<Pago>>('pagos/', { params }).then((r) => { setDatos(r.data); setError('') }).catch((e) => setError(mensajeDeError(e)))
    }, 250)
    return () => clearTimeout(t)
  }, [api, filtros, pagina])
  const filtrar = (c: Partial<typeof filtros>) => { setPagina(1); setFiltros({ ...filtros, ...c }) }
  const porForma = useMemo(() => {
    const totales = new Map<string, number>()
    datos?.results.filter((p) => p.estado === 'confirmado').forEach((p) => totales.set(p.forma_pago, (totales.get(p.forma_pago) ?? 0) + Number(p.importe)))
    return [...totales.entries()]
  }, [datos])

  return (
    <div>
      <Encabezado titulo="Historial de cobros" descripcion="Pagos contado y cobros con recibo. Los revertidos se conservan con su motivo." />
      <Aviso tipo="error">{error}</Aviso>
      <div className="mb-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Campo etiqueta="Cliente (código)"><input className="campo" value={filtros.cliente} onChange={(e) => filtrar({ cliente: e.target.value })} /></Campo>
        <Campo etiqueta="Origen">
          <select className="campo" value={filtros.origen} onChange={(e) => filtrar({ origen: e.target.value })}>
            <option value="">Todos</option><option value="contado">Factura contado</option><option value="recibo">Recibo</option>
          </select>
        </Campo>
        <Campo etiqueta="Estado">
          <select className="campo" value={filtros.estado} onChange={(e) => filtrar({ estado: e.target.value })}>
            <option value="">Todos</option><option value="confirmado">Confirmados</option><option value="revertido">Revertidos</option>
          </select>
        </Campo>
        <Campo etiqueta="Forma de pago">
          <select className="campo" value={filtros.forma_pago} onChange={(e) => filtrar({ forma_pago: e.target.value })}>
            <option value="">Todas</option>{formas.map((f) => <option key={f.Code} value={f.Code}>{f.nombre}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Desde"><input type="date" className="campo" value={filtros.desde} onChange={(e) => filtrar({ desde: e.target.value })} /></Campo>
        <Campo etiqueta="Hasta"><input type="date" className="campo" value={filtros.hasta} onChange={(e) => filtrar({ hasta: e.target.value })} /></Campo>
      </div>
      {porForma.length > 0 && datos && datos.count <= datos.results.length && (
        <p className="mb-3 text-sm">Confirmados por forma de pago: {porForma.map(([f, t]) => <span key={f} className="mr-3"><b>{f}</b> {gs(t)}</span>)}</p>
      )}
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Fecha</th><th>Cliente</th><th>Origen</th><th>Facturas</th><th>Forma de pago</th><th>Cobró</th><th className="text-right">Importe</th><th>Estado</th></tr></thead>
          <tbody>
            {datos?.results.map((p) => (
              <tr key={p.referencia} className={p.estado === 'revertido' ? 'text-koape-gris' : ''}>
                <td>{fechaHora(p.fecha_hora)}</td>
                <td>{p.cliente_nombre} <span className="text-xs text-koape-gris">{p.cliente}</span></td>
                <td>{p.recibo ? <Link className="text-koape-rojo hover:underline" to={`/panel/recibos/${p.recibo}`}>Recibo {p.recibo}</Link> : p.origen_nombre}</td>
                <td className="text-xs">{p.aplicaciones.map((a) => <Link key={a.factura} className="mr-1 hover:underline" to={`/panel/facturas/${a.factura}`}>{a.numero}</Link>)}</td>
                <td>{p.forma_pago}{p.referencia_externa ? <span className="text-xs text-koape-gris"> · {p.referencia_externa}</span> : null}</td>
                <td>{p.cobrado_por}</td>
                <td className="text-right font-semibold">{gs(p.importe)}</td>
                <td title={p.motivo_reversion}>{p.estado_nombre}</td>
              </tr>
            ))}
            {datos?.results.length === 0 && <tr><td colSpan={8} className="text-center text-koape-gris">Sin cobros en ese período.</td></tr>}
          </tbody>
        </table>
      </div>
      {datos && <Paginador pagina={pagina} total={datos.count} alCambiar={setPagina} />}
    </div>
  )
}

const TIPOS_FORMA: Record<FormaPago['tipo'], string> = { efectivo: 'Efectivo', transferencia: 'Transferencia', pos: 'POS (tarjeta)', otro: 'Otro medio' }

export function FormasPago() {
  const { api, puede } = useSesion()
  const [formas, setFormas] = useState<FormaPago[]>([])
  const [error, setError] = useState('')
  const [edicion, setEdicion] = useState<FormaPago | 'nueva' | null>(null)
  const gestiona = puede('cobranzas.formas_pago')

  const cargar = useCallback(() => {
    api.get<FormaPago[]>('formas-pago/').then((r) => setFormas(r.data)).catch((e) => setError(mensajeDeError(e)))
  }, [api])
  useEffect(cargar, [cargar])

  return (
    <div className="max-w-3xl">
      <Encabezado titulo="Formas de pago" descripcion="Medios con los que se cobra. La caja muestra un saldo separado por tipo (no se suman como dinero físico)."
        acciones={gestiona && <button className="boton-primario" onClick={() => setEdicion('nueva')}>Nueva forma de pago</button>} />
      <Aviso tipo="error">{error}</Aviso>
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Código</th><th>Nombre</th><th>Tipo</th><th>Pide referencia</th><th>Estado</th><th /></tr></thead>
          <tbody>
            {formas.map((f) => (
              <tr key={f.Code} className={f.activa ? '' : 'text-koape-gris'}>
                <td className="font-semibold">{f.Code}</td><td>{f.nombre}</td><td>{f.tipo_nombre}</td>
                <td>{f.requiere_referencia ? 'Sí' : 'No'}</td><td>{f.activa ? 'Activa' : 'Desactivada'}</td>
                <td>{gestiona && <button className="text-sm text-koape-rojo hover:underline" onClick={() => setEdicion(f)}>Editar</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {edicion && <EditarForma forma={edicion === 'nueva' ? null : edicion} alCerrar={() => setEdicion(null)} alGuardar={() => { setEdicion(null); cargar() }} />}
    </div>
  )
}

function EditarForma({ forma, alCerrar, alGuardar }: { forma: FormaPago | null; alCerrar: () => void; alGuardar: () => void }) {
  const { api } = useSesion()
  const [datos, setDatos] = useState({
    Code: forma?.Code ?? '', nombre: forma?.nombre ?? '', tipo: forma?.tipo ?? 'otro' as FormaPago['tipo'],
    requiere_referencia: forma?.requiere_referencia ?? false, orden: forma?.orden ?? 0, activa: forma?.activa ?? true,
  })
  const [error, setError] = useState('')

  async function guardar(e: FormEvent) {
    e.preventDefault()
    setError('')
    try {
      if (forma) await api.patch(`formas-pago/${encodeURIComponent(forma.Code)}/`, { ...datos, Code: undefined })
      else await api.post('formas-pago/', datos)
      alGuardar()
    } catch (err) {
      setError(mensajeDeError(err))
    }
  }

  return (
    <Modal titulo={forma ? `Forma de pago ${forma.Code}` : 'Nueva forma de pago'} alCerrar={alCerrar}>
      <form className="space-y-4" onSubmit={(e) => void guardar(e)}>
        <Aviso tipo="error">{error}</Aviso>
        {!forma && <Campo etiqueta="Código (no se cambia después)"><input className="campo" value={datos.Code} onChange={(e) => setDatos({ ...datos, Code: e.target.value })} /></Campo>}
        <Campo etiqueta="Nombre"><input className="campo" value={datos.nombre} onChange={(e) => setDatos({ ...datos, nombre: e.target.value })} /></Campo>
        <Campo etiqueta="Tipo">
          <select className="campo" value={datos.tipo} onChange={(e) => setDatos({ ...datos, tipo: e.target.value as FormaPago['tipo'] })}>
            {Object.entries(TIPOS_FORMA).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Orden en las listas"><input type="number" min={0} className="campo w-24" value={datos.orden} onChange={(e) => setDatos({ ...datos, orden: Number(e.target.value) || 0 })} /></Campo>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={datos.requiere_referencia} onChange={(e) => setDatos({ ...datos, requiere_referencia: e.target.checked })} /> Pide la referencia de la operación (n° de transferencia, voucher…)</label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={datos.activa} onChange={(e) => setDatos({ ...datos, activa: e.target.checked })} /> Activa</label>
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={!datos.nombre.trim() || (!forma && !datos.Code.trim())}>Guardar</button>
        </div>
      </form>
    </Modal>
  )
}
