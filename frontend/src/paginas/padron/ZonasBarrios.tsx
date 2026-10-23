import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { mensajeDeError } from '../../api/cliente'
import type { Barrio, Poligono, Zona } from '../../api/tipos'
import { Aviso } from '../../componentes/Aviso'
import { Campo } from '../../componentes/Campo'
import { Encabezado } from '../../componentes/Encabezado'
import { Modal } from '../../componentes/Modal'
import { EditorPoligono } from '../../mapa/EditorPoligono'
import { useSesion } from '../../sesion/ContextoSesion'

type Edicion = { tipo: 'zona'; zona: Zona | null } | { tipo: 'barrio'; barrio: Barrio | null; zona?: string }

export function ZonasBarrios() {
  const { api, puede } = useSesion()
  const [zonas, setZonas] = useState<Zona[]>([])
  const [barrios, setBarrios] = useState<Barrio[]>([])
  const [error, setError] = useState('')
  const [edicion, setEdicion] = useState<Edicion | null>(null)
  const [verArchivados, setVerArchivados] = useState(false)
  const gestiona = puede('territorio.gestionar')

  const cargar = useCallback(async () => {
    try {
      const [z, b] = await Promise.all([api.get<Zona[]>('zonas/'), api.get<Barrio[]>('barrios/')])
      setZonas(z.data)
      setBarrios(b.data)
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }, [api])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const visiblesZ = zonas.filter((z) => verArchivados || z.activa)
  const cerrar = () => setEdicion(null)
  const guardado = () => { setEdicion(null); void cargar() }

  return (
    <div>
      <Encabezado titulo="Zonas y barrios"
        descripcion="Cada barrio pertenece a una zona. No se borran: se archivan y siguen en el historial."
        acciones={gestiona && <button className="boton-primario" onClick={() => setEdicion({ tipo: 'zona', zona: null })}>Nueva zona</button>} />
      <Aviso tipo="error">{error}</Aviso>
      <label className="mb-4 flex items-center gap-2 text-sm text-koape-gris">
        <input type="checkbox" checked={verArchivados} onChange={(e) => setVerArchivados(e.target.checked)} /> Mostrar archivados
      </label>
      {visiblesZ.length === 0 && <p className="text-sm text-koape-gris">Todavía no hay zonas. Cree la primera.</p>}
      <div className="space-y-4">
        {visiblesZ.map((z) => (
          <div key={z.Code} className={`tarjeta p-5 ${z.activa ? '' : 'opacity-60'}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <span className="inline-block h-5 w-5 rounded-full border border-black/10" style={{ background: z.color }} />
                <div>
                  <p className="font-titulo text-lg font-bold">{z.nombre} <span className="text-sm font-normal text-koape-gris">{z.Code}</span></p>
                  <p className="text-xs text-koape-gris">{z.poligono ? 'Con polígono' : 'Sin polígono'}{z.activa ? '' : ' · archivada'}</p>
                </div>
              </div>
              {gestiona && (
                <div className="flex gap-2">
                  <button className="boton-secundario" onClick={() => setEdicion({ tipo: 'zona', zona: z })}>Editar</button>
                  {z.activa && <button className="boton-secundario" onClick={() => setEdicion({ tipo: 'barrio', barrio: null, zona: z.Code })}>Agregar barrio</button>}
                </div>
              )}
            </div>
            <ul className="mt-3 divide-y divide-koape-gris-claro/50 text-sm">
              {barrios.filter((b) => b.zona === z.Code && (verArchivados || b.activo)).map((b) => (
                <li key={b.Code} className={`flex items-center justify-between py-2 ${b.activo ? '' : 'text-koape-gris'}`}>
                  <span>{b.nombre} <span className="text-xs text-koape-gris">{b.Code}{b.activo ? '' : ' · archivado'}</span></span>
                  {gestiona && <button className="text-sm font-semibold text-koape-rojo hover:underline" onClick={() => setEdicion({ tipo: 'barrio', barrio: b })}>Editar</button>}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      {edicion?.tipo === 'zona' && <FormularioZona zona={edicion.zona} zonas={zonas} alCerrar={cerrar} alGuardar={guardado} />}
      {edicion?.tipo === 'barrio' && (
        <FormularioBarrio barrio={edicion.barrio} zonaInicial={edicion.zona} zonas={zonas} barrios={barrios} alCerrar={cerrar} alGuardar={guardado} />
      )}
    </div>
  )
}

function FormularioZona({ zona, zonas, alCerrar, alGuardar }: { zona: Zona | null; zonas: Zona[]; alCerrar: () => void; alGuardar: () => void }) {
  const { api } = useSesion()
  const [form, setForm] = useState({
    Code: zona?.Code ?? '', nombre: zona?.nombre ?? '', color: zona?.color ?? '#1D4ED8',
    observaciones: zona?.observaciones ?? '', activa: zona?.activa ?? true,
  })
  const [poligono, setPoligono] = useState<Poligono | null>(zona?.poligono ?? null)
  const [error, setError] = useState('')
  const contexto = useMemo(
    () => zonas.filter((z) => z.Code !== zona?.Code && z.activa).map((z) => ({ poligono: z.poligono, color: z.color, nombre: z.nombre })),
    [zonas, zona],
  )

  async function guardar(e: FormEvent) {
    e.preventDefault()
    setError('')
    try {
      const cuerpo = { ...form, poligono }
      if (zona) await api.patch(`zonas/${zona.Code}/`, cuerpo)
      else await api.post('zonas/', cuerpo)
      alGuardar()
    } catch (err) {
      setError(mensajeDeError(err))
    }
  }

  return (
    <Modal titulo={zona ? `Zona ${zona.nombre}` : 'Nueva zona'} alCerrar={alCerrar} amplio>
      <form onSubmit={guardar} className="space-y-4">
        <Aviso tipo="error">{error}</Aviso>
        <div className="grid gap-4 sm:grid-cols-[1fr_2fr_auto]">
          <Campo etiqueta="Código"><input className="campo uppercase" value={form.Code} disabled={!!zona} required maxLength={40} onChange={(e) => setForm({ ...form, Code: e.target.value })} /></Campo>
          <Campo etiqueta="Nombre"><input className="campo" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} /></Campo>
          <Campo etiqueta="Color"><input type="color" className="h-10 w-16 cursor-pointer rounded border border-koape-gris-claro" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value.toUpperCase() })} /></Campo>
        </div>
        <EditorPoligono valor={poligono} color={form.color} alCambiar={setPoligono} contexto={contexto} />
        <Campo etiqueta="Observaciones"><textarea className="campo" value={form.observaciones} onChange={(e) => setForm({ ...form, observaciones: e.target.value })} /></Campo>
        {zona && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.activa} onChange={(e) => setForm({ ...form, activa: e.target.checked })} />
            Activa (si se destilda, la zona queda archivada: no se le agregan barrios nuevos)
          </label>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={!form.Code.trim() || !form.nombre}>Guardar</button>
        </div>
      </form>
    </Modal>
  )
}

function FormularioBarrio({ barrio, zonaInicial, zonas, barrios, alCerrar, alGuardar }: {
  barrio: Barrio | null; zonaInicial?: string; zonas: Zona[]; barrios: Barrio[]; alCerrar: () => void; alGuardar: () => void
}) {
  const { api } = useSesion()
  const [form, setForm] = useState({
    zona: barrio?.zona ?? zonaInicial ?? zonas.find((z) => z.activa)?.Code ?? '', Code: barrio?.Code ?? '',
    nombre: barrio?.nombre ?? '', observaciones: barrio?.observaciones ?? '', activo: barrio?.activo ?? true,
  })
  const [poligono, setPoligono] = useState<Poligono | null>(barrio?.poligono ?? null)
  const [error, setError] = useState('')
  const zona = zonas.find((z) => z.Code === form.zona)
  const contexto = useMemo(() => [
    ...(zona?.poligono ? [{ poligono: zona.poligono, color: zona.color, nombre: `Zona ${zona.nombre}` }] : []),
    ...barrios.filter((b) => b.Code !== barrio?.Code && b.zona === form.zona && b.activo)
      .map((b) => ({ poligono: b.poligono, color: '#97989C', nombre: b.nombre })),
  ], [zona, barrios, barrio, form.zona])

  async function guardar(e: FormEvent) {
    e.preventDefault()
    setError('')
    try {
      const cuerpo = { ...form, poligono }
      if (barrio) await api.patch(`barrios/${barrio.Code}/`, cuerpo)
      else await api.post('barrios/', cuerpo)
      alGuardar()
    } catch (err) {
      setError(mensajeDeError(err))
    }
  }

  return (
    <Modal titulo={barrio ? `Barrio ${barrio.nombre}` : 'Nuevo barrio'} alCerrar={alCerrar} amplio>
      <form onSubmit={guardar} className="space-y-4">
        <Aviso tipo="error">{error}</Aviso>
        <div className="grid gap-4 sm:grid-cols-3">
          <Campo etiqueta="Zona">
            <select className="campo" value={form.zona} onChange={(e) => setForm({ ...form, zona: e.target.value })}>
              {zonas.filter((z) => z.activa || z.Code === barrio?.zona).map((z) => <option key={z.Code} value={z.Code}>{z.nombre}</option>)}
            </select>
          </Campo>
          <Campo etiqueta="Código"><input className="campo uppercase" value={form.Code} disabled={!!barrio} required maxLength={40} onChange={(e) => setForm({ ...form, Code: e.target.value })} /></Campo>
          <Campo etiqueta="Nombre"><input className="campo" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} /></Campo>
        </div>
        <p className="text-xs text-koape-gris">El polígono del barrio es opcional.</p>
        <EditorPoligono valor={poligono} color={zona?.color ?? '#1D4ED8'} alCambiar={setPoligono} contexto={contexto} />
        <Campo etiqueta="Observaciones"><textarea className="campo" value={form.observaciones} onChange={(e) => setForm({ ...form, observaciones: e.target.value })} /></Campo>
        {barrio && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.activo} onChange={(e) => setForm({ ...form, activo: e.target.checked })} />
            Activo (si se destilda, queda archivado: no se ofrece para conexiones nuevas)
          </label>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={!form.zona || !form.Code.trim() || !form.nombre}>Guardar</button>
        </div>
      </form>
    </Modal>
  )
}
