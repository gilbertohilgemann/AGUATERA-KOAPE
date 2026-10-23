import { useEffect, useState, type FormEvent } from 'react'
import { mensajeDeError } from '../api/cliente'
import type { Institucion } from '../api/tipos'
import { Aviso } from '../componentes/Aviso'
import { Campo } from '../componentes/Campo'
import { Encabezado } from '../componentes/Encabezado'
import { useSesion } from '../sesion/ContextoSesion'
import { fechaHora } from '../utilidades/fechas'

const EDITABLES = ['nombre', 'ruc', 'direccion', 'telefono', 'correo', 'contacto', 'zona_horaria', 'configuracion_regional'] as const
type Editable = (typeof EDITABLES)[number]

export function InstitucionPagina() {
  const { api, puede, refrescar } = useSesion()
  const [datos, setDatos] = useState<Institucion | null>(null)
  const [form, setForm] = useState<Record<Editable, string>>(() => Object.fromEntries(EDITABLES.map((c) => [c, ''])) as Record<Editable, string>)
  const [error, setError] = useState('')
  const [exito, setExito] = useState('')
  const [guardando, setGuardando] = useState(false)
  const [galeria, setGaleria] = useState(false)
  const [dias, setDias] = useState('30')
  const [reparto, setReparto] = useState<'manual' | 'automatica'>('manual')
  const [portal, setPortal] = useState(false)
  const editable = puede('institucion.editar')

  useEffect(() => {
    api.get<Institucion>('institucion/')
      .then((r) => {
        setDatos(r.data)
        setGaleria(r.data.lecturas_permite_galeria)
        setDias(String(r.data.dias_vencimiento_credito))
        setReparto(r.data.aplicacion_pagos)
        setPortal(r.data.portal_abonados)
        setForm(Object.fromEntries(EDITABLES.map((c) => [c, r.data[c] ?? ''])) as Record<Editable, string>)
      })
      .catch((e) => setError(mensajeDeError(e)))
  }, [api])

  async function guardar(e: FormEvent) {
    e.preventDefault()
    setError('')
    setExito('')
    setGuardando(true)
    try {
      const r = await api.patch<Institucion>('institucion/', { ...form, lecturas_permite_galeria: galeria, dias_vencimiento_credito: Number(dias) || 0, aplicacion_pagos: reparto, portal_abonados: portal })
      setDatos(r.data)
      setExito('Datos guardados.')
      await refrescar()
    } catch (err) {
      setError(mensajeDeError(err))
    } finally {
      setGuardando(false)
    }
  }

  const campo = (c: Editable, etiqueta: string, ancho = false, tipo = 'text') => (
    <Campo etiqueta={etiqueta} ancho={ancho}>
      <input type={tipo} className="campo" value={form[c]} disabled={!editable}
        onChange={(e) => setForm({ ...form, [c]: e.target.value })} />
    </Campo>
  )

  return (
    <div className="max-w-3xl">
      <Encabezado titulo="Institución" descripcion="Datos de su aguatera o junta de saneamiento." />
      <Aviso tipo="error">{error}</Aviso>
      {datos && (
        <form onSubmit={guardar} className="tarjeta space-y-5 p-6">
          <dl className="grid gap-3 text-sm sm:grid-cols-3">
            <div><dt className="etiqueta">Código</dt><dd className="font-semibold">{datos.codigo}</dd></div>
            <div><dt className="etiqueta">Estado</dt><dd>{datos.estado_nombre}</dd></div>
            <div><dt className="etiqueta">Facturación</dt><dd>{datos.modalidad_facturacion_nombre}</dd></div>
            <div><dt className="etiqueta">Alta</dt><dd>{fechaHora(datos.creado_en)}</dd></div>
          </dl>
          <p className="text-xs text-koape-gris">
            El código, el estado y la modalidad de facturación los define la plataforma (la modalidad depende de las
            habilitaciones fiscales de la institución).
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            {campo('nombre', 'Nombre o razón social', true)}
            {campo('ruc', 'RUC')}
            {campo('telefono', 'Teléfono')}
            {campo('correo', 'Correo electrónico', false, 'email')}
            {campo('direccion', 'Dirección', true)}
            <Campo etiqueta="Datos de contacto" ancho>
              <textarea className="campo min-h-24" value={form.contacto} disabled={!editable}
                onChange={(e) => setForm({ ...form, contacto: e.target.value })} />
            </Campo>
            {campo('zona_horaria', 'Zona horaria')}
            {campo('configuracion_regional', 'Configuración regional')}
          </div>
          <fieldset className="rounded-lg border border-koape-gris-claro p-4">
            <legend className="px-1 text-sm font-bold">Lecturas, facturación y cobros</legend>
            <label className="mb-3 flex items-center gap-2 text-sm">
              Las facturas a crédito vencen a los
              <input type="number" min={0} max={365} className="campo w-20" value={dias} disabled={!editable} onChange={(e) => setDias(e.target.value)} />
              días de emitidas.
            </label>
            <label className="mb-3 block text-sm">
              Al cobrar con recibo, el pago se reparte entre las facturas a crédito:
              <select className="campo mt-1" value={reparto} disabled={!editable} onChange={(e) => setReparto(e.target.value as 'manual' | 'automatica')}>
                <option value="manual">Manual: el cajero indica cuánto va a cada factura</option>
                <option value="automatica">Automático: primero la factura vencida más antigua</option>
              </select>
              <span className="text-xs text-koape-gris">En los dos casos el reparto se muestra antes de confirmar y se puede ajustar.</span>
            </label>
            <label className="mb-3 flex items-start gap-2 text-sm">
              <input type="checkbox" className="mt-1" checked={portal} disabled={!editable} onChange={(e) => setPortal(e.target.checked)} />
              <span>Ofrecer el <b>portal de abonados</b> (/portal): los clientes con un correo cargado en su ficha pueden consultar
                su deuda, facturas, pagos y lecturas. Para activarlo, el cliente usa su número de documento y ese correo.</span>
            </label>
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" className="mt-1" checked={galeria} disabled={!editable} onChange={(e) => setGaleria(e.target.checked)} />
              <span>Permitir que el cobrador use una foto de la <b>galería</b> del teléfono. Por defecto la foto del medidor se
                toma con la cámara en el momento; las lecturas con foto de galería quedan marcadas.</span>
            </label>
          </fieldset>
          <Aviso tipo="exito">{exito}</Aviso>
          {editable && <button className="boton-primario" disabled={guardando}>{guardando ? 'Guardando…' : 'Guardar'}</button>}
        </form>
      )}
    </div>
  )
}
