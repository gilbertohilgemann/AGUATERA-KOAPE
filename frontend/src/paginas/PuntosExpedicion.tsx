import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { mensajeDeError } from '../api/cliente'
import type { PuntoExpedicion, RangoNumeracion, TipoDocumento } from '../api/tipos'
import { Aviso } from '../componentes/Aviso'
import { Campo } from '../componentes/Campo'
import { Encabezado } from '../componentes/Encabezado'
import { Modal } from '../componentes/Modal'
import { useSesion } from '../sesion/ContextoSesion'

const TIPOS: Record<TipoDocumento, string> = { factura: 'Factura', nota_credito: 'Nota de crédito' }

type Edicion = { tipo: 'punto'; punto: PuntoExpedicion | null } | { tipo: 'rango'; rango: RangoNumeracion | null; punto: string }

/**
 * Puntos de expedición y rangos de numeración. Cada factura o nota de crédito toma su número (SerNr)
 * del rango activo y vigente de su punto; el contador interno no se muestra ni se edita.
 */
export function PuntosExpedicion() {
  const { api, puede } = useSesion()
  const [puntos, setPuntos] = useState<PuntoExpedicion[]>([])
  const [error, setError] = useState('')
  const [edicion, setEdicion] = useState<Edicion | null>(null)
  const gestiona = puede('facturacion.numeracion')

  const cargar = useCallback(async () => {
    try {
      setPuntos((await api.get<PuntoExpedicion[]>('puntos-expedicion/')).data)
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }, [api])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const guardado = () => { setEdicion(null); void cargar() }

  return (
    <div>
      <Encabezado titulo="Puntos de expedición"
        descripcion="Numeración de facturas y notas de crédito. Cada punto tiene sus rangos «desde–hasta» por tipo de documento."
        acciones={gestiona && <button className="boton-primario" onClick={() => setEdicion({ tipo: 'punto', punto: null })}>Nuevo punto</button>} />
      <Aviso tipo="error">{error}</Aviso>
      {puntos.length === 0 && <p className="text-sm text-koape-gris">Todavía no hay puntos de expedición.</p>}
      <div className="space-y-4">
        {puntos.map((p) => (
          <div key={p.Code} className={`tarjeta p-5 ${p.activo ? '' : 'opacity-60'}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-titulo text-lg font-bold">{p.prefijo} · {p.nombre} <span className="text-sm font-normal text-koape-gris">{p.Code}</span></p>
                <p className="text-xs text-koape-gris">{p.direccion || 'Sin dirección'}{p.activo ? '' : ' · desactivado'}</p>
              </div>
              {gestiona && (
                <div className="flex gap-2">
                  <button className="boton-secundario" onClick={() => setEdicion({ tipo: 'punto', punto: p })}>Editar</button>
                  {p.activo && <button className="boton-secundario" onClick={() => setEdicion({ tipo: 'rango', rango: null, punto: p.Code })}>Agregar rango</button>}
                </div>
              )}
            </div>
            {p.rangos.length === 0 ? <p className="mt-3 text-sm text-koape-gris">Sin rangos: este punto todavía no puede emitir documentos.</p> : (
              <div className="mt-3 overflow-x-auto">
                <table className="tabla">
                  <thead><tr><th>Código</th><th>Documento</th><th>Timbrado</th><th>Números</th><th>Vigencia</th><th>Situación</th><th /></tr></thead>
                  <tbody>
                    {p.rangos.map((r) => (
                      <tr key={r.Code} className={r.activo ? '' : 'text-koape-gris'}>
                        <td className="font-semibold">{r.Code}</td>
                        <td>{r.tipo_documento_nombre}</td>
                        <td>{r.timbrado || '—'}</td>
                        <td>{r.desde.toLocaleString('es-PY')} – {r.hasta.toLocaleString('es-PY')}</td>
                        <td>{r.vigencia_desde || r.vigencia_hasta ? `${r.vigencia_desde ?? '…'} a ${r.vigencia_hasta ?? '…'}` : 'Sin límite'}</td>
                        <td>{!r.activo ? 'Desactivado' : r.agotado ? 'Agotado' : r.en_uso ? 'En uso' : 'Sin usar'}</td>
                        <td className="text-right">{gestiona && <button className="text-sm font-semibold text-koape-rojo hover:underline" onClick={() => setEdicion({ tipo: 'rango', rango: r, punto: p.Code })}>Editar</button>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ))}
      </div>
      {edicion?.tipo === 'punto' && <FormularioPunto punto={edicion.punto} alCerrar={() => setEdicion(null)} alGuardar={guardado} />}
      {edicion?.tipo === 'rango' && <FormularioRango rango={edicion.rango} punto={edicion.punto} alCerrar={() => setEdicion(null)} alGuardar={guardado} />}
    </div>
  )
}

function FormularioPunto({ punto, alCerrar, alGuardar }: { punto: PuntoExpedicion | null; alCerrar: () => void; alGuardar: () => void }) {
  const { api } = useSesion()
  const [form, setForm] = useState({
    Code: punto?.Code ?? '', establecimiento: punto?.establecimiento ?? '001', punto: punto?.punto ?? '001',
    nombre: punto?.nombre ?? '', direccion: punto?.direccion ?? '', observaciones: punto?.observaciones ?? '', activo: punto?.activo ?? true,
  })
  const [error, setError] = useState('')
  const usado = !!punto?.rangos.some((r) => r.en_uso)

  async function guardar(e: FormEvent) {
    e.preventDefault()
    setError('')
    try {
      if (punto) await api.patch(`puntos-expedicion/${punto.Code}/`, form)
      else await api.post('puntos-expedicion/', form)
      alGuardar()
    } catch (err) {
      setError(mensajeDeError(err))
    }
  }

  return (
    <Modal titulo={punto ? `Punto ${punto.prefijo}` : 'Nuevo punto de expedición'} alCerrar={alCerrar}>
      <form onSubmit={guardar} className="space-y-4">
        <Aviso tipo="error">{error}</Aviso>
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo etiqueta="Código"><input className="campo uppercase" required maxLength={40} disabled={!!punto} value={form.Code} onChange={(e) => setForm({ ...form, Code: e.target.value })} placeholder="Ej. CENTRAL" /></Campo>
          <Campo etiqueta="Nombre"><input className="campo" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} placeholder="Ej. Oficina central" /></Campo>
          <Campo etiqueta="Establecimiento"><input className="campo" inputMode="numeric" maxLength={3} disabled={usado} value={form.establecimiento} onChange={(e) => setForm({ ...form, establecimiento: e.target.value })} /></Campo>
          <Campo etiqueta="Punto de expedición"><input className="campo" inputMode="numeric" maxLength={3} disabled={usado} value={form.punto} onChange={(e) => setForm({ ...form, punto: e.target.value })} /></Campo>
          <Campo etiqueta="Dirección" ancho><input className="campo" value={form.direccion} onChange={(e) => setForm({ ...form, direccion: e.target.value })} /></Campo>
          <Campo etiqueta="Observaciones" ancho><textarea className="campo" value={form.observaciones} onChange={(e) => setForm({ ...form, observaciones: e.target.value })} /></Campo>
        </div>
        {usado && <p className="text-xs text-koape-gris">Ya emitió documentos: el establecimiento y el número de punto no se cambian.</p>}
        {punto && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.activo} onChange={(e) => setForm({ ...form, activo: e.target.checked })} /> Activo
          </label>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={!form.Code.trim() || !form.nombre.trim()}>Guardar</button>
        </div>
      </form>
    </Modal>
  )
}

function FormularioRango({ rango, punto, alCerrar, alGuardar }: { rango: RangoNumeracion | null; punto: string; alCerrar: () => void; alGuardar: () => void }) {
  const { api } = useSesion()
  const [form, setForm] = useState({
    Code: rango?.Code ?? '', tipo_documento: rango?.tipo_documento ?? 'factura' as TipoDocumento, timbrado: rango?.timbrado ?? '',
    desde: String(rango?.desde ?? 1), hasta: String(rango?.hasta ?? ''), vigencia_desde: rango?.vigencia_desde ?? '',
    vigencia_hasta: rango?.vigencia_hasta ?? '', observaciones: rango?.observaciones ?? '', activo: rango?.activo ?? true,
  })
  const [error, setError] = useState('')
  const fijo = !!rango?.en_uso

  async function guardar(e: FormEvent) {
    e.preventDefault()
    setError('')
    const cuerpo = {
      ...form, punto, desde: Number(form.desde), hasta: Number(form.hasta),
      vigencia_desde: form.vigencia_desde || null, vigencia_hasta: form.vigencia_hasta || null,
    }
    try {
      if (rango) await api.patch(`rangos-numeracion/${rango.Code}/`, cuerpo)
      else await api.post('rangos-numeracion/', cuerpo)
      alGuardar()
    } catch (err) {
      setError(mensajeDeError(err))
    }
  }

  return (
    <Modal titulo={rango ? `Rango ${rango.Code}` : 'Nuevo rango de numeración'} alCerrar={alCerrar}>
      <form onSubmit={guardar} className="space-y-4">
        <Aviso tipo="error">{error}</Aviso>
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo etiqueta="Código"><input className="campo uppercase" required maxLength={40} disabled={!!rango} value={form.Code} onChange={(e) => setForm({ ...form, Code: e.target.value })} placeholder="Ej. FAC-2026" /></Campo>
          <Campo etiqueta="Tipo de documento">
            <select className="campo" disabled={fijo} value={form.tipo_documento} onChange={(e) => setForm({ ...form, tipo_documento: e.target.value as TipoDocumento })}>
              {Object.entries(TIPOS).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
            </select>
          </Campo>
          <Campo etiqueta="Timbrado"><input className="campo" disabled={fijo} value={form.timbrado} onChange={(e) => setForm({ ...form, timbrado: e.target.value })} /></Campo>
          <div />
          <Campo etiqueta="Desde el número"><input className="campo" inputMode="numeric" disabled={fijo} value={form.desde} onChange={(e) => setForm({ ...form, desde: e.target.value })} /></Campo>
          <Campo etiqueta="Hasta el número"><input className="campo" inputMode="numeric" value={form.hasta} onChange={(e) => setForm({ ...form, hasta: e.target.value })} /></Campo>
          <Campo etiqueta="Vigente desde"><input type="date" className="campo" value={form.vigencia_desde} onChange={(e) => setForm({ ...form, vigencia_desde: e.target.value })} /></Campo>
          <Campo etiqueta="Vigente hasta"><input type="date" className="campo" value={form.vigencia_hasta} onChange={(e) => setForm({ ...form, vigencia_hasta: e.target.value })} /></Campo>
          <Campo etiqueta="Observaciones" ancho><textarea className="campo" value={form.observaciones} onChange={(e) => setForm({ ...form, observaciones: e.target.value })} /></Campo>
        </div>
        {fijo && <p className="text-xs text-koape-gris">Este rango ya se usó: solo se puede ampliar «hasta», cambiar la vigencia u observaciones, o desactivarlo.</p>}
        {rango && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.activo} onChange={(e) => setForm({ ...form, activo: e.target.checked })} /> Activo
          </label>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={!form.Code.trim() || !form.desde || !form.hasta}>Guardar</button>
        </div>
      </form>
    </Modal>
  )
}
