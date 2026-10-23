import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { mensajeDeError } from '../../api/cliente'
import type { Factura, Pagina, PendientesCliente } from '../../api/tipos'
import { Aviso } from '../../componentes/Aviso'
import { Campo } from '../../componentes/Campo'
import { Encabezado } from '../../componentes/Encabezado'
import { Modal } from '../../componentes/Modal'
import { Paginador } from '../../componentes/Paginador'
import { useSesion } from '../../sesion/ContextoSesion'
import { fechaHora } from '../../utilidades/fechas'
import { useAbrirPdf } from '../lecturas/Lecturas'
import { AvisoCajaCerrada } from '../caja/Caja'
import { BuscadorCliente } from '../padron/BuscadorCliente'
import { gs, num } from '../tarifas/Tarifas'

const fecha = (v: string | null) => (v ? new Date(`${v}T12:00:00`).toLocaleDateString('es-PY') : '—')

const COLOR: Record<Factura['estado'], string> = {
  emitida: 'bg-emerald-100 text-emerald-800', en_tramite: 'bg-sky-100 text-sky-800',
  rechazada: 'bg-rose-100 text-rose-800', anulada: 'bg-slate-200 text-slate-600',
}

const COBRO: Record<string, [string, string]> = {
  pagada: ['Pagada', 'bg-emerald-100 text-emerald-800'], parcial: ['Pago parcial', 'bg-amber-100 text-amber-800'],
  pendiente: ['Impaga', 'bg-slate-100 text-slate-700'], vencida: ['Vencida', 'bg-rose-100 text-rose-800'],
}

export function InsigniaCobro({ estado }: { estado: string }) {
  const c = COBRO[estado]
  return c ? <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${c[1]}`}>{c[0]}</span> : null
}

export function InsigniaFactura({ f }: { f: Pick<Factura, 'estado' | 'estado_nombre'> }) {
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${COLOR[f.estado]}`}>{f.estado_nombre}</span>
}

/** Caja: el usuario viene a pagar → se eligen sus liquidaciones pendientes y se emite la factura. */
export function Facturar() {
  const { api } = useSesion()
  const navegar = useNavigate()
  const [cliente, setCliente] = useState<{ Code: string; nombre: string } | null>(null)
  const [datos, setDatos] = useState<PendientesCliente | null>(null)
  const [elegidas, setElegidas] = useState<string[]>([])
  const [condicion, setCondicion] = useState<'contado' | 'credito'>('contado')
  const [punto, setPunto] = useState('')
  const [observaciones, setObservaciones] = useState('')
  const [error, setError] = useState('')
  const [emitiendo, setEmitiendo] = useState(false)
  const [recarga, setRecarga] = useState(0)
  const [forma, setForma] = useState('')
  const [referencia, setReferencia] = useState('')

  useEffect(() => {
    if (!cliente) return
    let vigente = true // descarta respuestas de un cliente elegido antes
    setDatos(null)
    setElegidas([])
    api.get<PendientesCliente>('facturacion/pendientes/', { params: { cliente: cliente.Code } })
      .then((r) => {
        if (!vigente) return
        setDatos(r.data)
        setElegidas(r.data.pendientes.map((p) => p.numero))
        setPunto((actual) => (r.data.puntos.some((p) => p.Code === actual) ? actual : r.data.puntos[0]?.Code ?? ''))
        setForma((actual) => (r.data.formas_pago.some((f) => f.Code === actual) ? actual : r.data.formas_pago[0]?.Code ?? ''))
      })
      .catch((e) => { if (vigente) setError(mensajeDeError(e)) })
    return () => { vigente = false }
  }, [api, cliente, recarga])

  const alternar = (n: string) => setElegidas(elegidas.includes(n) ? elegidas.filter((x) => x !== n) : [...elegidas, n])
  const formaElegida = datos?.formas_pago.find((f) => f.Code === forma)
  const faltaPago = condicion === 'contado' && (!formaElegida || (formaElegida.requiere_referencia && !referencia.trim()))
  const total = datos?.pendientes.filter((p) => elegidas.includes(p.numero)).reduce((s, p) => s + Number(p.total), 0) ?? 0

  async function emitir() {
    if (!cliente) return
    setError('')
    setEmitiendo(true)
    try {
      const pago = condicion === 'contado' ? { forma_pago: forma, referencia_externa: referencia } : {}
      const r = await api.post<Factura>('facturas/', { cliente: cliente.Code, liquidaciones: elegidas, condicion, punto: punto || null, observaciones, ...pago })
      setReferencia('')
      navegar(`/panel/facturas/${r.data.referencia}`)
    } catch (e) {
      setError(mensajeDeError(e))
      setRecarga((n) => n + 1) // otra caja pudo facturar alguna: se muestra lo que queda pendiente
    } finally {
      setEmitiendo(false)
    }
  }

  return (
    <div className="max-w-4xl">
      <Encabezado titulo="Facturar" descripcion="Cuando el usuario viene a pagar: elija sus liquidaciones pendientes y emita la factura. Cada liquidación se factura entera y una sola vez." />
      <Aviso tipo="error">{error}</Aviso>
      <AvisoCajaCerrada />
      <div className="tarjeta space-y-4 p-5">
        <Campo etiqueta="Cliente (titular)"><BuscadorCliente valor={cliente} alElegir={(c) => { setError(''); setCliente(c) }} /></Campo>
        {datos && datos.modalidad === 'no_configurada' && <Aviso tipo="error">La institución todavía no tiene habilitada una modalidad de facturación. La configura la plataforma según sus habilitaciones fiscales.</Aviso>}
        {datos && (
          <>
            <p className="text-sm text-koape-gris">RUC / C.I.: <b className="text-koape-tinta">{datos.cliente.documento || 'sin cargar'}</b> · Dirección: {datos.cliente.direccion || '—'}
              {!datos.cliente.documento && <span className="text-koape-rojo"> (cárguelo en Clientes si la factura lo necesita)</span>}</p>
            {datos.pendientes.length === 0 ? <p className="text-sm text-koape-gris">No tiene liquidaciones pendientes de facturar.</p> : (
              <div className="overflow-x-auto">
                <table className="tabla">
                  <thead><tr><th /><th>Período</th><th>Conexión</th><th>Tarifa</th><th>Consumo</th><th className="text-right">Importe</th></tr></thead>
                  <tbody>
                    {datos.pendientes.map((p) => (
                      <tr key={p.numero}>
                        <td><input type="checkbox" checked={elegidas.includes(p.numero)} onChange={() => alternar(p.numero)} aria-label={`Facturar ${p.numero}`} /></td>
                        <td>{p.periodo}</td>
                        <td>{p.conexion} <span className="text-xs text-koape-gris">{p.direccion}</span></td>
                        <td>{p.tarifa}</td>
                        <td>{num(p.consumo)} m³</td>
                        <td className="text-right">{gs(p.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {datos.pendientes.length > 0 && (
              <div className="grid gap-4 sm:grid-cols-3">
                <Campo etiqueta="Condición de venta">
                  <select className="campo" value={condicion} onChange={(e) => setCondicion(e.target.value as 'contado' | 'credito')}>
                    <option value="contado">Contado</option>
                    <option value="credito">Crédito (vence a los {datos.dias_vencimiento_credito} días)</option>
                  </select>
                </Campo>
                <Campo etiqueta="Punto de expedición">
                  <select className="campo" value={punto} onChange={(e) => setPunto(e.target.value)}>
                    {datos.puntos.map((p) => <option key={p.Code} value={p.Code}>{p.prefijo} · {p.nombre}</option>)}
                  </select>
                </Campo>
                <Campo etiqueta="Observaciones"><input className="campo" value={observaciones} onChange={(e) => setObservaciones(e.target.value)} /></Campo>
                {condicion === 'contado' && (
                  <>
                    <Campo etiqueta="Forma de pago">
                      <select className="campo" value={forma} onChange={(e) => setForma(e.target.value)}>
                        {datos.formas_pago.map((f) => <option key={f.Code} value={f.Code}>{f.nombre}</option>)}
                      </select>
                    </Campo>
                    {formaElegida?.requiere_referencia && (
                      <Campo etiqueta="Referencia de la operación"><input className="campo" placeholder="N° de transferencia o voucher" value={referencia} onChange={(e) => setReferencia(e.target.value)} /></Campo>
                    )}
                  </>
                )}
              </div>
            )}
            {datos.pendientes.length > 0 && (
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-koape-gris-claro pt-4">
                <p className="text-lg">Total a facturar: <b className="text-2xl">{gs(total)}</b></p>
                <button className="boton-primario" disabled={emitiendo || !elegidas.length || !punto || faltaPago || datos.modalidad === 'no_configurada'} onClick={() => void emitir()}>
                  {emitiendo ? 'Emitiendo…' : condicion === 'credito' ? 'Emitir factura a crédito' : 'Cobrar y emitir factura contado'}
                </button>
              </div>
            )}
            <p className="text-xs text-koape-gris">Contado: el pago queda registrado junto con la factura. Para pagar en partes, emita la factura a crédito y cobre después con recibos (Cobranzas → Cobrar).</p>
          </>
        )}
      </div>
    </div>
  )
}

export function Facturas() {
  const { api, puede } = useSesion()
  const [filtros, setFiltros] = useState({ buscar: '', estado: '', condicion: '', desde: '', hasta: '', con_saldo: '' })
  const [pagina, setPagina] = useState(1)
  const [datos, setDatos] = useState<Pagina<Factura> | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const t = setTimeout(() => {
      const params = Object.fromEntries(Object.entries({ ...filtros, pagina }).filter(([, v]) => v !== ''))
      api.get<Pagina<Factura>>('facturas/', { params }).then((r) => { setDatos(r.data); setError('') }).catch((e) => setError(mensajeDeError(e)))
    }, 250)
    return () => clearTimeout(t)
  }, [api, filtros, pagina])
  const filtrar = (c: Partial<typeof filtros>) => { setPagina(1); setFiltros({ ...filtros, ...c }) }

  return (
    <div>
      <Encabezado titulo="Facturas" descripcion="Facturas emitidas, con su número fiscal y estado."
        acciones={puede('facturacion.emitir') && <Link className="boton-primario" to="/panel/facturar">Facturar</Link>} />
      <Aviso tipo="error">{error}</Aviso>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Campo etiqueta="Buscar"><input className="campo" placeholder="Número, cliente, RUC" value={filtros.buscar} onChange={(e) => filtrar({ buscar: e.target.value })} /></Campo>
        <Campo etiqueta="Estado">
          <select className="campo" value={filtros.estado} onChange={(e) => filtrar({ estado: e.target.value })}>
            <option value="">Todos</option><option value="emitida">Emitidas</option><option value="en_tramite">En trámite</option>
            <option value="rechazada">Rechazadas</option><option value="anulada">Anuladas</option>
          </select>
        </Campo>
        <Campo etiqueta="Condición">
          <select className="campo" value={filtros.condicion} onChange={(e) => filtrar({ condicion: e.target.value })}>
            <option value="">Todas</option><option value="contado">Contado</option><option value="credito">Crédito</option>
          </select>
        </Campo>
        <label className="flex items-center gap-2 self-end pb-2 text-sm"><input type="checkbox" checked={filtros.con_saldo === '1'} onChange={(e) => filtrar({ con_saldo: e.target.checked ? '1' : '' })} /> Solo con saldo pendiente</label>
        <Campo etiqueta="Desde"><input type="date" className="campo" value={filtros.desde} onChange={(e) => filtrar({ desde: e.target.value })} /></Campo>
        <Campo etiqueta="Hasta"><input type="date" className="campo" value={filtros.hasta} onChange={(e) => filtrar({ hasta: e.target.value })} /></Campo>
      </div>
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Número</th><th>Fecha</th><th>Cliente</th><th>Condición</th><th>Vence</th><th className="text-right">Total</th><th className="text-right">Saldo</th><th>Estado</th></tr></thead>
          <tbody>
            {datos?.results.map((f) => (
              <tr key={f.referencia} className={f.estado === 'anulada' ? 'text-koape-gris' : ''}>
                <td><Link className="font-semibold text-koape-rojo hover:underline" to={`/panel/facturas/${f.referencia}`}>{f.numero}</Link></td>
                <td>{fecha(f.fecha_emision)}</td>
                <td>{f.cliente_nombre}</td>
                <td>{f.condicion_nombre}</td>
                <td>{fecha(f.fecha_vencimiento)}</td>
                <td className="text-right font-semibold">{gs(f.total)}</td>
                <td className="text-right">{f.estado === 'emitida' ? gs(f.saldo) : '—'}</td>
                <td><InsigniaFactura f={f} /> <InsigniaCobro estado={f.estado_cobro} /></td>
              </tr>
            ))}
            {datos?.results.length === 0 && <tr><td colSpan={8} className="text-center text-koape-gris">Sin facturas.</td></tr>}
          </tbody>
        </table>
      </div>
      {datos && <Paginador pagina={pagina} total={datos.count} alCambiar={setPagina} />}
    </div>
  )
}

export function FichaFactura() {
  const { referencia = '' } = useParams()
  const { api, puede } = useSesion()
  const abrirPdf = useAbrirPdf()
  const [f, setF] = useState<Factura | null>(null)
  const [error, setError] = useState('')
  const [exito, setExito] = useState('')
  const [anulando, setAnulando] = useState(false)
  const [motivo, setMotivo] = useState('')
  const [procesando, setProcesando] = useState(false)
  const ruta = `facturas/${encodeURIComponent(referencia)}/`

  const cargar = useCallback(() => {
    api.get<Factura>(ruta).then((r) => setF(r.data)).catch((e) => setError(mensajeDeError(e)))
  }, [api, ruta])
  useEffect(cargar, [cargar])

  async function accion(sub: string, cuerpo: object, mensaje: string) {
    if (procesando) return
    setProcesando(true)
    setError('')
    setExito('')
    try {
      setF((await api.post<Factura>(`${ruta}${sub}/`, cuerpo)).data)
      setExito(mensaje)
      setAnulando(false)
    } catch (e) {
      setError(mensajeDeError(e))
      cargar()
    } finally {
      setProcesando(false)
    }
  }

  if (!f) return error ? <Aviso tipo="error">{error}</Aviso> : <p className="text-koape-gris">Cargando…</p>
  return (
    <div className="max-w-4xl space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm"><Link className="text-koape-rojo hover:underline" to="/panel/facturas">← Facturas</Link></p>
          <h1 className="text-2xl font-extrabold">Factura {f.numero}</h1>
          <p className="text-sm text-koape-gris">Timbrado {f.timbrado || '—'} · {f.modalidad === 'autoimpresa' ? 'Autoimpresa' : 'Electrónica'} · emitida {fechaHora(f.creado_en)} por {f.emitida_por}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <InsigniaFactura f={f} />
          <InsigniaCobro estado={f.estado_cobro} />
          {f.estado === 'emitida' && f.condicion === 'credito' && Number(f.saldo) > 0 && puede('cobranzas.registrar') && <Link className="boton-primario" to={`/panel/cobrar?cliente=${encodeURIComponent(f.cliente)}`}>Cobrar</Link>}
          {f.modalidad === 'autoimpresa' && <button className="boton-primario" onClick={() => void abrirPdf(`${ruta}pdf/`)}>Imprimir (PDF)</button>}
          {f.electronica && ['desconocido', 'enviada', 'en_proceso'].includes(f.electronica.estado) && puede('facturacion.emitir') && <button className="boton-secundario" disabled={procesando} onClick={() => void accion('consultar-estado', {}, 'Estado consultado.')}>Consultar estado</button>}
          {f.electronica && ['pendiente', 'error_recuperable'].includes(f.electronica.estado) && puede('facturacion.emitir') && <button className="boton-secundario" disabled={procesando} onClick={() => void accion('reintentar', {}, 'Enviada de nuevo.')}>Reintentar envío</button>}
          {f.estado === 'emitida' && f.modalidad === 'autoimpresa' && puede('facturacion.anular') && <button className="boton-secundario" onClick={() => setAnulando(true)}>Anular</button>}
        </div>
      </div>
      <Aviso tipo="error">{error}</Aviso>
      <Aviso tipo="exito">{exito}</Aviso>
      {f.estado === 'anulada' && <Aviso tipo="error">Anulada {fechaHora(f.anulada_en)} por {f.anulada_por}: {f.motivo_anulacion}. Sus liquidaciones volvieron a quedar para facturar.</Aviso>}
      {f.electronica && <Aviso tipo={f.electronica.estado === 'rechazada' ? 'error' : 'exito'}>Proveedor {f.electronica.proveedor}: {f.electronica.estado_nombre}{f.electronica.ultimo_error ? ` — ${f.electronica.ultimo_error}` : ''}{f.cdc ? ` · CDC ${f.cdc}` : ''}</Aviso>}
      <section className="tarjeta p-5">
        <dl className="grid gap-3 text-sm sm:grid-cols-3">
          <div><dt className="etiqueta">Cliente</dt><dd className="font-semibold">{f.cliente_nombre}</dd><dd className="text-xs text-koape-gris">RUC/C.I. {f.cliente_documento || '—'}</dd></div>
          <div><dt className="etiqueta">Fecha</dt><dd>{fecha(f.fecha_emision)}</dd></div>
          <div><dt className="etiqueta">Condición</dt><dd>{f.condicion_nombre}{f.fecha_vencimiento ? ` · vence ${fecha(f.fecha_vencimiento)}` : ''}</dd></div>
        </dl>
      </section>
      <section className="tarjeta overflow-x-auto p-5">
        <table className="tabla">
          <thead><tr><th>Descripción</th><th>Cant.</th><th className="text-right">Exentas</th><th className="text-right">5 %</th><th className="text-right">10 %</th></tr></thead>
          <tbody>
            {f.lineas.map((l, n) => (
              <tr key={n}>
                <td>{l.descripcion}</td>
                <td>{l.tipo === 'porcentaje' ? '' : num(l.cantidad)}</td>
                <td className="text-right">{l.iva === 'exento' ? gs(l.total_linea) : ''}</td>
                <td className="text-right">{l.iva === '5' ? gs(l.total_linea) : ''}</td>
                <td className="text-right">{l.iva === '10' ? gs(l.total_linea) : ''}</td>
              </tr>
            ))}
          </tbody>
          <tfoot className="text-sm">
            <tr><td colSpan={2}>Subtotales</td><td className="text-right">{gs(f.subtotal_exento)}</td><td className="text-right">{gs(f.subtotal_iva5)}</td><td className="text-right">{gs(f.subtotal_iva10)}</td></tr>
            <tr><td colSpan={4}>Liquidación del IVA (5 %: {gs(f.iva5)} · 10 %: {gs(f.iva10)})</td><td /></tr>
            <tr className="font-extrabold"><td colSpan={4}>Total a pagar</td><td className="text-right text-lg">{gs(f.total)}</td></tr>
          </tfoot>
        </table>
      </section>
      <section className="tarjeta p-5 text-sm">
        <h2 className="mb-2 font-bold">Cobros</h2>
        <p className="mb-2">Total {gs(f.total)} · pagado <b>{gs(f.pagado)}</b> · saldo <b>{gs(f.saldo)}</b></p>
        {f.pagos.length === 0 ? <p className="text-koape-gris">Sin cobros registrados.</p> : (
          <ul className="space-y-1">
            {f.pagos.map((p, n) => (
              <li key={n} className={p.estado !== 'vigente' ? 'text-koape-gris line-through' : ''}>
                {fechaHora(p.fecha_hora)} · {gs(p.importe)} · {p.forma_pago}{p.referencia_externa ? ` (${p.referencia_externa})` : ''} · {p.origen === 'contado' ? 'pago contado' : <>recibo <Link className="text-koape-rojo hover:underline" to={`/panel/recibos/${p.recibo}`}>{p.recibo}</Link></>} · {p.usuario}{p.estado !== 'vigente' ? ' (revertido)' : ''}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="tarjeta p-5 text-sm">
        <h2 className="mb-2 font-bold">Liquidaciones facturadas</h2>
        <ul className="space-y-1">
          {f.liquidaciones.map((q) => (
            <li key={q.numero}><Link className="text-koape-rojo hover:underline" to={`/panel/liquidaciones/${q.numero}`}>{q.numero}</Link> · {q.conexion} · {q.periodo} · {gs(q.importe)}{q.estado !== 'vigente' ? ' (liberada)' : ''}</li>
          ))}
        </ul>
      </section>
      {anulando && (
        <Modal titulo="Anular factura" alCerrar={() => setAnulando(false)}>
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); void accion('anular', { motivo }, 'Factura anulada.') }}>
            <p className="text-sm">La factura queda anulada en el historial (con su número) y sus liquidaciones vuelven a quedar para facturar.{f.condicion === 'contado' ? ' Su pago contado queda revertido.' : ''} Si tiene cobros con recibo, anule antes esos recibos.</p>
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
