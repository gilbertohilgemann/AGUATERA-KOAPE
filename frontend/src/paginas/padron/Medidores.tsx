import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { mensajeDeError } from '../../api/cliente'
import type { Instalacion, Medidor, Pagina } from '../../api/tipos'
import { Aviso } from '../../componentes/Aviso'
import { Campo } from '../../componentes/Campo'
import { Encabezado } from '../../componentes/Encabezado'
import { Modal } from '../../componentes/Modal'
import { Paginador } from '../../componentes/Paginador'
import { useSesion } from '../../sesion/ContextoSesion'

const ESTADOS: Record<Medidor['estado'], string> = {
  disponible: 'Disponible', instalado: 'Instalado', retirado: 'Retirado', danado: 'Dañado', baja: 'Dado de baja',
}

export function Medidores() {
  const { api, puede } = useSesion()
  const [medidores, setMedidores] = useState<Medidor[]>([])
  const [total, setTotal] = useState(0)
  const [pagina, setPagina] = useState(1)
  const [buscar, setBuscar] = useState('')
  const [estado, setEstado] = useState('')
  const [error, setError] = useState('')
  const [editando, setEditando] = useState<Medidor | 'nuevo' | null>(null)
  const [historial, setHistorial] = useState<Medidor | null>(null)

  const cargar = useCallback(async () => {
    try {
      const r = await api.get<Pagina<Medidor>>('medidores/', { params: { buscar: buscar || undefined, estado: estado || undefined, pagina } })
      setMedidores(r.data.results)
      setTotal(r.data.count)
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }, [api, buscar, estado, pagina])

  useEffect(() => {
    void cargar()
  }, [cargar])

  return (
    <div>
      <Encabezado titulo="Medidores" descripcion="Medidores físicos. Se instalan, retiran o sustituyen desde la ficha de cada conexión."
        acciones={puede('padron.medidores') && <button className="boton-primario" onClick={() => setEditando('nuevo')}>Nuevo medidor</button>} />
      <Aviso tipo="error">{error}</Aviso>
      <div className="mb-4 flex flex-wrap gap-3">
        <input className="campo max-w-xs" placeholder="Buscar por código, número, marca o modelo" value={buscar} onChange={(e) => { setPagina(1); setBuscar(e.target.value) }} />
        <select className="campo max-w-xs" value={estado} onChange={(e) => { setPagina(1); setEstado(e.target.value) }}>
          <option value="">Todos los estados</option>
          {Object.entries(ESTADOS).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
        </select>
      </div>
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Código</th><th>Número</th><th>Marca / modelo</th><th>Capacidad</th><th>Estado</th><th>Conexión</th><th /></tr></thead>
          <tbody>
            {medidores.map((m) => (
              <tr key={m.Code}>
                <td className="font-semibold">{m.Code}</td>
                <td className="font-mono">{m.numero || '—'}</td>
                <td>{[m.marca, m.modelo].filter(Boolean).join(' · ') || '—'}</td>
                <td>{m.lectura_maxima ? `${Number(m.lectura_maxima)} ${m.unidad}` : '—'}</td>
                <td>{m.estado_nombre}</td>
                <td>{m.conexion_actual ? <Link className="text-koape-rojo hover:underline" to={`/panel/conexiones/${m.conexion_actual}`}>{m.conexion_actual}</Link> : '—'}</td>
                <td className="whitespace-nowrap text-right">
                  <button className="text-sm font-semibold text-koape-magenta hover:underline" onClick={() => setHistorial(m)}>Historial</button>
                  {puede('padron.medidores') && <button className="ml-3 text-sm font-semibold text-koape-rojo hover:underline" onClick={() => setEditando(m)}>Editar</button>}
                </td>
              </tr>
            ))}
            {medidores.length === 0 && <tr><td colSpan={7} className="text-center text-koape-gris">Sin resultados.</td></tr>}
          </tbody>
        </table>
      </div>
      <Paginador pagina={pagina} total={total} alCambiar={setPagina} />
      {editando && <FormularioMedidor medidor={editando === 'nuevo' ? null : editando} alCerrar={() => setEditando(null)} alGuardar={() => { setEditando(null); void cargar() }} />}
      {historial && <HistorialMedidor medidor={historial} alCerrar={() => setHistorial(null)} />}
    </div>
  )
}

function FormularioMedidor({ medidor, alCerrar, alGuardar }: { medidor: Medidor | null; alCerrar: () => void; alGuardar: () => void }) {
  const { api } = useSesion()
  const [form, setForm] = useState({
    Code: medidor?.Code ?? '', numero: medidor?.numero ?? '', marca: medidor?.marca ?? '', modelo: medidor?.modelo ?? '', unidad: medidor?.unidad ?? 'm3',
    lectura_maxima: medidor?.lectura_maxima ?? '', observaciones: medidor?.observaciones ?? '', estado: medidor?.estado ?? 'disponible',
  })
  const [error, setError] = useState('')
  const instalado = medidor?.estado === 'instalado'

  async function guardar(e: FormEvent) {
    e.preventDefault()
    setError('')
    const cuerpo = { ...form, lectura_maxima: form.lectura_maxima === '' ? null : form.lectura_maxima }
    try {
      if (medidor) await api.patch(`medidores/${medidor.Code}/`, cuerpo)
      else await api.post('medidores/', cuerpo)
      alGuardar()
    } catch (err) {
      setError(mensajeDeError(err))
    }
  }

  return (
    <Modal titulo={medidor ? `Medidor ${medidor.Code}` : 'Nuevo medidor'} alCerrar={alCerrar}>
      <form onSubmit={guardar} className="space-y-4">
        <Aviso tipo="error">{error}</Aviso>
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo etiqueta="Código"><input className="campo uppercase" value={form.Code} disabled={!!medidor} required maxLength={40} onChange={(e) => setForm({ ...form, Code: e.target.value })} /></Campo>
          <Campo etiqueta="Número del medidor (el grabado en el aparato)"><input className="campo font-mono uppercase" value={form.numero} maxLength={40} title="Letras, números y - . / (sin espacios)" placeholder="Ej. A23057X" onChange={(e) => setForm({ ...form, numero: e.target.value.replace(/\s/g, '') })} /></Campo>
          <Campo etiqueta="Unidad"><input className="campo" value={form.unidad} onChange={(e) => setForm({ ...form, unidad: e.target.value })} /></Campo>
          <Campo etiqueta="Marca"><input className="campo" value={form.marca} onChange={(e) => setForm({ ...form, marca: e.target.value })} /></Campo>
          <Campo etiqueta="Modelo"><input className="campo" value={form.modelo} onChange={(e) => setForm({ ...form, modelo: e.target.value })} /></Campo>
          <Campo etiqueta="Lectura máxima (vuelve a cero)"><input className="campo" inputMode="decimal" value={form.lectura_maxima} onChange={(e) => setForm({ ...form, lectura_maxima: e.target.value })} placeholder="Ej. 99999" /></Campo>
          <Campo etiqueta="Estado">
            <select className="campo" value={form.estado} disabled={instalado} onChange={(e) => setForm({ ...form, estado: e.target.value as Medidor['estado'] })}>
              {(instalado ? ['instalado'] : ['disponible', 'retirado', 'danado', 'baja']).map((v) => <option key={v} value={v}>{ESTADOS[v as Medidor['estado']]}</option>)}
            </select>
          </Campo>
          <Campo etiqueta="Observaciones" ancho><textarea className="campo" value={form.observaciones} onChange={(e) => setForm({ ...form, observaciones: e.target.value })} /></Campo>
        </div>
        {instalado && <p className="text-xs text-koape-gris">Está instalado: su estado cambia al retirarlo desde la conexión.</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={!form.Code.trim()}>Guardar</button>
        </div>
      </form>
    </Modal>
  )
}

function HistorialMedidor({ medidor, alCerrar }: { medidor: Medidor; alCerrar: () => void }) {
  const { api } = useSesion()
  const [filas, setFilas] = useState<Instalacion[] | null>(null)
  useEffect(() => {
    api.get<Instalacion[]>(`medidores/${medidor.Code}/historial/`).then((r) => setFilas(r.data)).catch(() => setFilas([]))
  }, [api, medidor])
  return (
    <Modal titulo={`Historial del medidor ${medidor.Code}`} alCerrar={alCerrar} amplio>
      {!filas ? <p className="text-sm text-koape-gris">Cargando…</p> : <TablaInstalaciones filas={filas} mostrarConexion />}
    </Modal>
  )
}

export function TablaInstalaciones({ filas, mostrarConexion = false }: { filas: Instalacion[]; mostrarConexion?: boolean }) {
  if (filas.length === 0) return <p className="text-sm text-koape-gris">Nunca fue instalado.</p>
  return (
    <div className="overflow-x-auto">
      <table className="tabla">
        <thead><tr>{mostrarConexion ? <th>Conexión</th> : <th>Medidor</th>}<th>Instalado</th><th>Lectura inicial</th><th>Retirado</th><th>Lectura de retiro</th><th>Motivo</th></tr></thead>
        <tbody>
          {filas.map((i, n) => (
            <tr key={`${i.conexion}-${i.medidor}-${i.fecha_instalacion}-${n}`}>
              <td className="font-semibold">{mostrarConexion ? i.conexion : i.medidor}{!mostrarConexion && i.medidor_numero && <span className="block font-mono text-xs font-normal text-koape-gris">N.º {i.medidor_numero}</span>}</td>
              <td>{i.fecha_instalacion}</td>
              <td>{Number(i.lectura_inicial)}</td>
              <td>{i.fecha_retiro ?? <span className="font-semibold text-emerald-700">Vigente</span>}</td>
              <td>{i.lectura_retiro !== null ? Number(i.lectura_retiro) : '—'}</td>
              <td>{i.motivo_retiro || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
