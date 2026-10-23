import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { mensajeDeError } from '../../api/cliente'
import type { Cliente, ConexionDetalle, EstadoConexion, Medidor, Pagina, Tarifa } from '../../api/tipos'
import { Aviso } from '../../componentes/Aviso'
import { Campo } from '../../componentes/Campo'
import { FotoPrivada } from '../../componentes/FotoPrivada'
import { Modal } from '../../componentes/Modal'
import { SelectorUbicacion, type Ubicacion } from '../../mapa/SelectorUbicacion'
import { useSesion } from '../../sesion/ContextoSesion'
import { comprimirImagen } from '../../utilidades/imagenes'
import { BuscadorCliente } from './BuscadorCliente'
import { InsigniaEstado, useTerritorio } from './Conexiones'
import { TablaInstalaciones } from './Medidores'
import { LecturasDeConexion } from '../lecturas/Lecturas'

const hoy = () => new Date().toLocaleDateString('en-CA') // AAAA-MM-DD en la zona del navegador
/** Coordenada con 6 decimales (≈ 11 cm), lo que guarda el servidor; vacío = sin ubicación. */
const coordenada = (v: string) => (v.trim() === '' || Number.isNaN(Number(v)) ? (v.trim() || null) : Number(v).toFixed(6))

function Bloque({ titulo, children, acciones }: { titulo: string; children: ReactNode; acciones?: ReactNode }) {
  return (
    <section className="tarjeta p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold">{titulo}</h2>
        {acciones}
      </div>
      {children}
    </section>
  )
}

/** Alta de una conexión. */
export function NuevaConexion() {
  const { api } = useSesion()
  const navegar = useNavigate()
  const [parametros] = useSearchParams()
  const { barrios } = useTerritorio()
  const [cliente, setCliente] = useState<Cliente | null>(null)
  const [form, setForm] = useState({ Code: '', direccion: '', barrio: '', estado: 'en_instalacion', fecha_instalacion: '', observaciones: '' })
  const [ubicacion, setUbicacion] = useState<Ubicacion>({ latitud: '', longitud: '', metodo_ubicacion: 'sin_ubicacion', precision_metros: null })
  const [error, setError] = useState('')

  useEffect(() => {
    const code = parametros.get('cliente')
    if (code) api.get<Cliente>(`clientes/${encodeURIComponent(code)}/`).then((r) => setCliente(r.data)).catch(() => undefined)
  }, [api, parametros])

  async function guardar(e: FormEvent) {
    e.preventDefault()
    setError('')
    if (!cliente) return
    try {
      const r = await api.post<ConexionDetalle>('conexiones/', {
        ...form, cliente: cliente.Code, barrio: form.barrio || null,
        fecha_instalacion: form.fecha_instalacion || null,
        latitud: coordenada(ubicacion.latitud), longitud: coordenada(ubicacion.longitud),
        metodo_ubicacion: ubicacion.metodo_ubicacion, precision_metros: ubicacion.precision_metros,
      })
      navegar(`/panel/conexiones/${r.data.Code}`, { replace: true })
    } catch (err) {
      setError(mensajeDeError(err))
    }
  }

  return (
    <form onSubmit={guardar} className="max-w-4xl space-y-4">
      <h1 className="text-2xl font-extrabold">Nueva conexión</h1>
      <Aviso tipo="error">{error}</Aviso>
      <Bloque titulo="Datos">
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo etiqueta="Titular" ancho><BuscadorCliente valor={cliente} alElegir={setCliente} /></Campo>
          <Campo etiqueta="Código"><input className="campo uppercase" required maxLength={40} placeholder="Ej. CX-0001" value={form.Code} onChange={(e) => setForm({ ...form, Code: e.target.value })} /></Campo>
          <Campo etiqueta="Estado inicial">
            <select className="campo" value={form.estado} onChange={(e) => setForm({ ...form, estado: e.target.value })}>
              <option value="en_instalacion">En instalación</option><option value="pendiente_ubicacion">Pendiente de ubicación</option><option value="activa">Activa</option>
            </select>
          </Campo>
          <Campo etiqueta="Dirección" ancho><input className="campo" value={form.direccion} onChange={(e) => setForm({ ...form, direccion: e.target.value })} /></Campo>
          <Campo etiqueta="Barrio">
            <select className="campo" value={form.barrio} onChange={(e) => setForm({ ...form, barrio: e.target.value })}>
              <option value="">Sin barrio</option>
              {barrios.filter((b) => b.activo).map((b) => <option key={b.Code} value={b.Code}>{b.zona_nombre} / {b.nombre}</option>)}
            </select>
          </Campo>
          <Campo etiqueta="Fecha de instalación"><input type="date" className="campo" value={form.fecha_instalacion} onChange={(e) => setForm({ ...form, fecha_instalacion: e.target.value })} /></Campo>
          <Campo etiqueta="Observaciones" ancho><textarea className="campo" value={form.observaciones} onChange={(e) => setForm({ ...form, observaciones: e.target.value })} /></Campo>
        </div>
      </Bloque>
      <Bloque titulo="Ubicación"><SelectorUbicacion valor={ubicacion} alCambiar={setUbicacion} /></Bloque>
      <div className="flex justify-end gap-2">
        <Link className="boton-secundario" to="/panel/conexiones">Cancelar</Link>
        <button className="boton-primario" disabled={!cliente || !form.Code.trim()}>Crear conexión</button>
      </div>
    </form>
  )
}

type Dialogo = 'estado' | 'titular' | 'instalar' | 'retirar' | 'sustituir' | null

/** Ficha de una conexión: datos, ubicación, foto, medidor, estado, titular e historial. */
export function FichaConexion() {
  const { code } = useParams()
  const id = encodeURIComponent(code ?? '')
  const { api, puede } = useSesion()
  const { barrios } = useTerritorio()
  const [conexion, setConexion] = useState<ConexionDetalle | null>(null)
  const [error, setError] = useState('')
  const [exito, setExito] = useState('')
  const [dialogo, setDialogo] = useState<Dialogo>(null)
  const [form, setForm] = useState({ direccion: '', barrio: '', tarifa: '', fecha_instalacion: '', observaciones: '' })
  const [ubicacion, setUbicacion] = useState<Ubicacion>({ latitud: '', longitud: '', metodo_ubicacion: 'sin_ubicacion', precision_metros: null })
  const [tarifas, setTarifas] = useState<Tarifa[]>([])
  const [versionFoto, setVersionFoto] = useState(0)
  const editable = puede('padron.conexiones') && conexion?.estado !== 'archivada'

  const aplicar = useCallback((c: ConexionDetalle) => {
    setConexion(c)
    setForm({ direccion: c.direccion, barrio: c.barrio ?? '', tarifa: c.tarifa ?? '', fecha_instalacion: c.fecha_instalacion ?? '', observaciones: c.observaciones })
    setUbicacion({ latitud: c.latitud ?? '', longitud: c.longitud ?? '', metodo_ubicacion: c.metodo_ubicacion, precision_metros: c.precision_metros })
  }, [])

  useEffect(() => {
    api.get<ConexionDetalle>(`conexiones/${id}/`).then((r) => aplicar(r.data)).catch((e) => setError(mensajeDeError(e)))
  }, [api, id, aplicar])

  useEffect(() => {
    api.get<Tarifa[]>('tarifas/').then((r) => setTarifas(r.data)).catch(() => setTarifas([]))
  }, [api])

  async function guardar(e: FormEvent) {
    e.preventDefault()
    setError('')
    setExito('')
    try {
      const r = await api.patch<ConexionDetalle>(`conexiones/${id}/`, {
        ...form, barrio: form.barrio || null, tarifa: form.tarifa || null, fecha_instalacion: form.fecha_instalacion || null,
        latitud: coordenada(ubicacion.latitud), longitud: coordenada(ubicacion.longitud),
        metodo_ubicacion: ubicacion.metodo_ubicacion, precision_metros: ubicacion.precision_metros,
      })
      aplicar(r.data)
      setExito('Cambios guardados.')
    } catch (err) {
      setError(mensajeDeError(err))
    }
  }

  async function subirFoto(archivo: File | undefined) {
    if (!archivo) return
    setError('')
    try {
      const datos = new FormData()
      datos.append('archivo', await comprimirImagen(archivo), 'vivienda.jpg')
      const r = await api.post<ConexionDetalle>(`conexiones/${id}/foto-vivienda/`, datos)
      aplicar(r.data)
      setVersionFoto((v) => v + 1)
    } catch (err) {
      setError(mensajeDeError(err))
    }
  }

  if (!conexion) return error ? <Aviso tipo="error">{error}</Aviso> : <p className="text-koape-gris">Cargando…</p>
  const vigente = conexion.instalaciones.find((i) => !i.fecha_retiro)
  const despues = (c: ConexionDetalle, mensaje: string) => { aplicar(c); setDialogo(null); setExito(mensaje) }

  return (
    <div className="max-w-5xl space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm"><Link className="text-koape-rojo hover:underline" to="/panel/conexiones">← Conexiones</Link></p>
          <h1 className="text-2xl font-extrabold">Conexión {conexion.Code}</h1>
          <p className="text-sm text-koape-gris">Titular: <b className="text-koape-tinta">{conexion.cliente_nombre}</b> ({conexion.cliente})</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <InsigniaEstado estado={conexion.estado} nombre={conexion.estado_nombre} />
          {puede('padron.conexiones') && conexion.transiciones.length > 0 && <button className="boton-secundario" onClick={() => setDialogo('estado')}>Cambiar estado</button>}
          {editable && <button className="boton-secundario" onClick={() => setDialogo('titular')}>Cambiar titular</button>}
        </div>
      </div>
      <Aviso tipo="error">{error}</Aviso>
      <Aviso tipo="exito">{exito}</Aviso>

      <form onSubmit={guardar} className="grid gap-4 lg:grid-cols-[1fr_1fr]">
        <Bloque titulo="Datos">
          <div className="grid gap-4">
            <Campo etiqueta="Dirección"><input className="campo" disabled={!editable} value={form.direccion} onChange={(e) => setForm({ ...form, direccion: e.target.value })} /></Campo>
            <Campo etiqueta="Barrio">
              <select className="campo" disabled={!editable} value={form.barrio} onChange={(e) => setForm({ ...form, barrio: e.target.value })}>
                <option value="">Sin barrio</option>
                {barrios.filter((b) => b.activo || b.Code === form.barrio).map((b) => <option key={b.Code} value={b.Code}>{b.zona_nombre} / {b.nombre}{b.activo ? '' : ' (archivado)'}</option>)}
              </select>
            </Campo>
            <Campo etiqueta="Tipo de conexión (tarifa)">
              <select className="campo" disabled={!editable} value={form.tarifa} onChange={(e) => setForm({ ...form, tarifa: e.target.value })}>
                <option value="">Por defecto{tarifas.find((t) => t.por_defecto) ? ` (${tarifas.find((t) => t.por_defecto)?.nombre})` : ''}</option>
                {tarifas.filter((t) => t.activa || t.Code === form.tarifa).map((t) => <option key={t.Code} value={t.Code}>{t.nombre}</option>)}
                {form.tarifa && !tarifas.some((t) => t.Code === form.tarifa) && <option value={form.tarifa}>{conexion.tarifa_nombre || form.tarifa}</option>}
              </select>
            </Campo>
            <Campo etiqueta="Fecha de instalación"><input type="date" className="campo" disabled={!editable} value={form.fecha_instalacion} onChange={(e) => setForm({ ...form, fecha_instalacion: e.target.value })} /></Campo>
            <Campo etiqueta="Observaciones"><textarea className="campo" disabled={!editable} value={form.observaciones} onChange={(e) => setForm({ ...form, observaciones: e.target.value })} /></Campo>
          </div>
        </Bloque>
        <Bloque titulo="Ubicación">
          {editable ? <SelectorUbicacion valor={ubicacion} alCambiar={setUbicacion} /> : (
            <p className="text-sm">{conexion.latitud ? `${conexion.latitud}, ${conexion.longitud} (${conexion.metodo_ubicacion_nombre})` : 'Sin ubicación.'}</p>
          )}
        </Bloque>
        {editable && <div className="lg:col-span-2 flex justify-end"><button className="boton-primario">Guardar cambios</button></div>}
      </form>

      <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
        <Bloque titulo="Foto de la vivienda"
          acciones={editable && (
            <label className="boton-secundario cursor-pointer">
              {conexion.tiene_foto_vivienda ? 'Cambiar foto' : 'Subir foto'}
              <input type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => void subirFoto(e.target.files?.[0])} />
            </label>
          )}>
          {conexion.tiene_foto_vivienda
            ? <FotoPrivada ruta={`conexiones/${conexion.Code}/foto-vivienda/`} version={String(versionFoto)} alt="Vivienda" className="max-h-72 w-full rounded-lg object-cover" />
            : <p className="text-sm text-koape-gris">Sin foto.</p>}
        </Bloque>
        <Bloque titulo="Medidor"
          acciones={puede('padron.medidores') && conexion.estado !== 'archivada' && conexion.estado !== 'desconectada' && (
            vigente ? (
              <div className="flex gap-2">
                <button className="boton-secundario" onClick={() => setDialogo('sustituir')}>Sustituir</button>
                <button className="boton-secundario" onClick={() => setDialogo('retirar')}>Retirar</button>
              </div>
            ) : <button className="boton-primario" onClick={() => setDialogo('instalar')}>Instalar medidor</button>
          )}>
          {vigente ? (
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <div><dt className="etiqueta">Código</dt><dd className="text-lg font-bold">{vigente.medidor}</dd></div>
              <div><dt className="etiqueta">Número del medidor</dt><dd className="font-mono text-lg">{vigente.medidor_numero || '—'}</dd></div>
              <div><dt className="etiqueta">Instalado</dt><dd>{vigente.fecha_instalacion}</dd></div>
              <div><dt className="etiqueta">Lectura inicial</dt><dd>{Number(vigente.lectura_inicial)}</dd></div>
              <div><dt className="etiqueta">Responsable</dt><dd>{vigente.instalado_por_nombre || '—'}</dd></div>
            </dl>
          ) : <p className="text-sm text-koape-gris">La conexión no tiene medidor instalado.</p>}
        </Bloque>
      </div>

      <LecturasDeConexion conexion={conexion.Code} />
      <Bloque titulo="Historial de medidores"><TablaInstalaciones filas={conexion.instalaciones} /></Bloque>
      <Bloque titulo="Historial de titulares">
        <ul className="divide-y divide-koape-gris-claro/50 text-sm">
          {conexion.titularidades.map((t, n) => (
            <li key={`${t.cliente}-${t.desde}-${n}`} className="py-2"><b>{t.cliente_nombre}</b> ({t.cliente}) · desde {t.desde}{t.hasta ? ` hasta ${t.hasta}` : ' (actual)'}{t.motivo ? ` · ${t.motivo}` : ''}</li>
          ))}
        </ul>
      </Bloque>

      {dialogo === 'estado' && <DialogoEstado conexion={conexion} alCerrar={() => setDialogo(null)} alListo={(c) => despues(c, 'Estado actualizado.')} />}
      {dialogo === 'titular' && <DialogoTitular conexion={conexion} alCerrar={() => setDialogo(null)} alListo={(c) => despues(c, 'Titular cambiado.')} />}
      {(dialogo === 'instalar' || dialogo === 'sustituir') && (
        <DialogoInstalar conexion={conexion} sustituir={dialogo === 'sustituir'} alCerrar={() => setDialogo(null)}
          alListo={(c) => despues(c, dialogo === 'sustituir' ? 'Medidor sustituido.' : 'Medidor instalado.')} />
      )}
      {dialogo === 'retirar' && <DialogoRetirar conexion={conexion} alCerrar={() => setDialogo(null)} alListo={(c) => despues(c, 'Medidor retirado.')} />}
    </div>
  )
}

function useEnvio(alListo: (c: ConexionDetalle) => void) {
  const { api } = useSesion()
  const [error, setError] = useState('')
  const [codigo, setCodigo] = useState('')
  const [enviando, setEnviando] = useState(false)
  async function enviar(ruta: string, cuerpo: object) {
    setError('')
    setCodigo('')
    setEnviando(true)
    try {
      const r = await api.post<ConexionDetalle>(ruta, cuerpo)
      alListo(r.data)
    } catch (err) {
      setError(mensajeDeError(err))
      const datos = (err as { response?: { data?: { codigo?: string } } }).response?.data
      setCodigo(datos?.codigo ?? '')
    } finally {
      setEnviando(false)
    }
  }
  return { error, codigo, enviando, enviar }
}

function DialogoEstado({ conexion, alCerrar, alListo }: { conexion: ConexionDetalle; alCerrar: () => void; alListo: (c: ConexionDetalle) => void }) {
  const [estado, setEstado] = useState<EstadoConexion>(conexion.transiciones[0].estado)
  const [motivo, setMotivo] = useState('')
  const { error, enviando, enviar } = useEnvio(alListo)
  return (
    <Modal titulo="Cambiar estado" alCerrar={alCerrar}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); void enviar(`conexiones/${conexion.Code}/estado/`, { estado, motivo }) }}>
        <Aviso tipo="error">{error}</Aviso>
        <p className="text-sm">Estado actual: <b>{conexion.estado_nombre}</b>. Suspender o desconectar no borra deudas ni historial.</p>
        <Campo etiqueta="Nuevo estado">
          <select className="campo" value={estado} onChange={(e) => setEstado(e.target.value as EstadoConexion)}>
            {conexion.transiciones.map((t) => <option key={t.estado} value={t.estado}>{t.nombre}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Motivo (obligatorio, queda en la auditoría)"><textarea className="campo" value={motivo} onChange={(e) => setMotivo(e.target.value)} /></Campo>
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={enviando || !motivo.trim()}>Confirmar</button>
        </div>
      </form>
    </Modal>
  )
}

function DialogoTitular({ conexion, alCerrar, alListo }: { conexion: ConexionDetalle; alCerrar: () => void; alListo: (c: ConexionDetalle) => void }) {
  const [cliente, setCliente] = useState<Cliente | null>(null)
  const [desde, setDesde] = useState(hoy())
  const [motivo, setMotivo] = useState('')
  const { error, enviando, enviar } = useEnvio(alListo)
  return (
    <Modal titulo="Cambiar titular" alCerrar={alCerrar}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); if (cliente) void enviar(`conexiones/${conexion.Code}/titular/`, { cliente: cliente.Code, desde, motivo }) }}>
        <Aviso tipo="error">{error}</Aviso>
        <p className="text-sm">Titular actual: <b>{conexion.cliente_nombre}</b>. Queda en el historial con la fecha del cambio.</p>
        <Campo etiqueta="Nuevo titular"><BuscadorCliente valor={cliente} alElegir={setCliente} /></Campo>
        <Campo etiqueta="Desde"><input type="date" className="campo" value={desde} onChange={(e) => setDesde(e.target.value)} /></Campo>
        <Campo etiqueta="Motivo"><input className="campo" value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Ej. venta de la vivienda" /></Campo>
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={enviando || !cliente || !motivo.trim()}>Confirmar</button>
        </div>
      </form>
    </Modal>
  )
}

const ESTADOS_RETIRO = [['retirado', 'Retirado (puede reinstalarse)'], ['danado', 'Dañado'], ['baja', 'Dado de baja'], ['disponible', 'Disponible']]

function DialogoInstalar({ conexion, sustituir, alCerrar, alListo }: { conexion: ConexionDetalle; sustituir: boolean; alCerrar: () => void; alListo: (c: ConexionDetalle) => void }) {
  const { api } = useSesion()
  const [medidores, setMedidores] = useState<Medidor[]>([])
  const [form, setForm] = useState({ medidor: '', fecha: hoy(), lectura_inicial: '0', lectura_retiro: '', motivo: '', estado_medidor_retirado: 'retirado', aceptar_lectura_menor: false })
  const { error, codigo, enviando, enviar } = useEnvio(alListo)

  useEffect(() => {
    api.get<Pagina<Medidor>>('medidores/', { params: { instalables: 1, tamanio: 200 } }).then((r) => setMedidores(r.data.results)).catch(() => setMedidores([]))
  }, [api])

  function confirmar(e: FormEvent) {
    e.preventDefault()
    if (sustituir) void enviar(`conexiones/${conexion.Code}/sustituir-medidor/`, form)
    else void enviar(`conexiones/${conexion.Code}/instalar-medidor/`, { medidor: form.medidor, fecha: form.fecha, lectura_inicial: form.lectura_inicial })
  }

  return (
    <Modal titulo={sustituir ? 'Sustituir medidor' : 'Instalar medidor'} alCerrar={alCerrar}>
      <form className="space-y-4" onSubmit={confirmar}>
        <Aviso tipo="error">{error}</Aviso>
        {sustituir && <p className="text-sm">El medidor actual se retira con su lectura final y queda en el historial; las lecturas anteriores siguen asociadas a él.</p>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo etiqueta="Medidor nuevo" ancho>
            <select className="campo" value={form.medidor} onChange={(e) => setForm({ ...form, medidor: e.target.value })}>
              <option value="">Elegir…</option>
              {medidores.map((m) => <option key={m.Code} value={m.Code}>{m.Code}{m.numero ? ` · N.º ${m.numero}` : ''}{m.marca ? ` · ${m.marca}` : ''} ({m.estado_nombre})</option>)}
            </select>
          </Campo>
          <Campo etiqueta="Fecha"><input type="date" className="campo" value={form.fecha} onChange={(e) => setForm({ ...form, fecha: e.target.value })} /></Campo>
          <Campo etiqueta="Lectura inicial del nuevo"><input className="campo" inputMode="decimal" value={form.lectura_inicial} onChange={(e) => setForm({ ...form, lectura_inicial: e.target.value })} /></Campo>
          {sustituir && (
            <>
              <Campo etiqueta="Lectura final del actual"><input className="campo" inputMode="decimal" value={form.lectura_retiro} onChange={(e) => setForm({ ...form, lectura_retiro: e.target.value })} /></Campo>
              <Campo etiqueta="El medidor retirado queda">
                <select className="campo" value={form.estado_medidor_retirado} onChange={(e) => setForm({ ...form, estado_medidor_retirado: e.target.value })}>
                  {ESTADOS_RETIRO.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                </select>
              </Campo>
              <Campo etiqueta="Motivo" ancho><input className="campo" value={form.motivo} onChange={(e) => setForm({ ...form, motivo: e.target.value })} /></Campo>
            </>
          )}
        </div>
        {codigo === 'lectura_menor' && (
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={form.aceptar_lectura_menor} onChange={(e) => setForm({ ...form, aceptar_lectura_menor: e.target.checked })} />
            Confirmo que la lectura final es menor que la inicial (el contador volvió a cero u otra situación explicada en el motivo).
          </label>
        )}
        {medidores.length === 0 && <p className="text-xs text-koape-gris">No hay medidores disponibles. Cárguelos en Medidores.</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={enviando || !form.medidor || (sustituir && (!form.lectura_retiro || !form.motivo.trim()))}>Confirmar</button>
        </div>
      </form>
    </Modal>
  )
}

function DialogoRetirar({ conexion, alCerrar, alListo }: { conexion: ConexionDetalle; alCerrar: () => void; alListo: (c: ConexionDetalle) => void }) {
  const [form, setForm] = useState({ fecha: hoy(), lectura_retiro: '', motivo: '', estado_medidor: 'retirado', aceptar_lectura_menor: false })
  const { error, codigo, enviando, enviar } = useEnvio(alListo)
  return (
    <Modal titulo="Retirar medidor" alCerrar={alCerrar}>
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); void enviar(`conexiones/${conexion.Code}/retirar-medidor/`, form) }}>
        <Aviso tipo="error">{error}</Aviso>
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo etiqueta="Fecha"><input type="date" className="campo" value={form.fecha} onChange={(e) => setForm({ ...form, fecha: e.target.value })} /></Campo>
          <Campo etiqueta="Lectura final"><input className="campo" inputMode="decimal" value={form.lectura_retiro} onChange={(e) => setForm({ ...form, lectura_retiro: e.target.value })} /></Campo>
          <Campo etiqueta="El medidor queda">
            <select className="campo" value={form.estado_medidor} onChange={(e) => setForm({ ...form, estado_medidor: e.target.value })}>
              {ESTADOS_RETIRO.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
            </select>
          </Campo>
          <Campo etiqueta="Motivo"><input className="campo" value={form.motivo} onChange={(e) => setForm({ ...form, motivo: e.target.value })} /></Campo>
        </div>
        {codigo === 'lectura_menor' && (
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={form.aceptar_lectura_menor} onChange={(e) => setForm({ ...form, aceptar_lectura_menor: e.target.checked })} />
            Confirmo que la lectura final es menor que la inicial (explicado en el motivo).
          </label>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={enviando || !form.lectura_retiro || !form.motivo.trim()}>Confirmar</button>
        </div>
      </form>
    </Modal>
  )
}
