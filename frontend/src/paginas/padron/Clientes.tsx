import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { mensajeDeError } from '../../api/cliente'
import type { Cliente, ConexionResumen, Pagina } from '../../api/tipos'
import { Aviso } from '../../componentes/Aviso'
import { Campo } from '../../componentes/Campo'
import { Encabezado } from '../../componentes/Encabezado'
import { Modal } from '../../componentes/Modal'
import { Paginador } from '../../componentes/Paginador'
import { useSesion } from '../../sesion/ContextoSesion'

const VACIO = {
  Code: '', nombre: '', tipo_persona: 'fisica' as Cliente['tipo_persona'], documento: '', telefono: '', correo: '',
  direccion_referencia: '', observaciones: '', estado: 'activo' as Cliente['estado'],
}

export function Clientes() {
  const { api, puede } = useSesion()
  const [clientes, setClientes] = useState<Cliente[]>([])
  const [total, setTotal] = useState(0)
  const [pagina, setPagina] = useState(1)
  const [buscar, setBuscar] = useState('')
  const [archivados, setArchivados] = useState(false)
  const [error, setError] = useState('')
  const [editando, setEditando] = useState<Cliente | 'nuevo' | null>(null)
  const [viendo, setViendo] = useState<Cliente | null>(null)

  const cargar = useCallback(async () => {
    try {
      const r = await api.get<Pagina<Cliente>>('clientes/', {
        params: { buscar: buscar || undefined, pagina, incluir_archivados: archivados ? 1 : undefined },
      })
      setClientes(r.data.results)
      setTotal(r.data.count)
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }, [api, buscar, pagina, archivados])

  useEffect(() => {
    void cargar()
  }, [cargar])

  return (
    <div>
      <Encabezado titulo="Clientes" descripcion="Titulares del servicio. Un cliente puede tener varias conexiones."
        acciones={puede('padron.clientes') && <button className="boton-primario" onClick={() => setEditando('nuevo')}>Nuevo cliente</button>} />
      <Aviso tipo="error">{error}</Aviso>
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <input className="campo max-w-sm" placeholder="Buscar por nombre, código, documento o teléfono" value={buscar}
          onChange={(e) => { setPagina(1); setBuscar(e.target.value) }} />
        <label className="flex items-center gap-2 text-sm text-koape-gris">
          <input type="checkbox" checked={archivados} onChange={(e) => { setPagina(1); setArchivados(e.target.checked) }} /> Incluir archivados
        </label>
      </div>
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Código</th><th>Nombre</th><th>Documento</th><th>Teléfono</th><th>Conexiones</th><th>Estado</th><th /></tr></thead>
          <tbody>
            {clientes.map((c) => (
              <tr key={c.Code} className={c.estado === 'archivado' ? 'text-koape-gris' : ''}>
                <td className="font-semibold">{c.Code}</td>
                <td>{c.nombre}</td>
                <td>{c.documento || '—'}</td>
                <td>{c.telefono || '—'}</td>
                <td>{c.cantidad_conexiones}</td>
                <td>{c.estado_nombre}</td>
                <td className="whitespace-nowrap text-right">
                  <button className="text-sm font-semibold text-koape-magenta hover:underline" onClick={() => setViendo(c)}>Conexiones</button>
                  {puede('padron.clientes') && <button className="ml-3 text-sm font-semibold text-koape-rojo hover:underline" onClick={() => setEditando(c)}>Editar</button>}
                </td>
              </tr>
            ))}
            {clientes.length === 0 && <tr><td colSpan={7} className="text-center text-koape-gris">Sin resultados.</td></tr>}
          </tbody>
        </table>
      </div>
      <Paginador pagina={pagina} total={total} alCambiar={setPagina} />
      {editando && <FormularioCliente cliente={editando === 'nuevo' ? null : editando} alCerrar={() => setEditando(null)} alGuardar={() => { setEditando(null); void cargar() }} />}
      {viendo && <ConexionesDelCliente cliente={viendo} alCerrar={() => setViendo(null)} />}
    </div>
  )
}

export function FormularioCliente({ cliente, alCerrar, alGuardar }: { cliente: Cliente | null; alCerrar: () => void; alGuardar: (c: Cliente) => void }) {
  const { api } = useSesion()
  const [form, setForm] = useState(() => (cliente ? {
    Code: cliente.Code, nombre: cliente.nombre, tipo_persona: cliente.tipo_persona, documento: cliente.documento,
    telefono: cliente.telefono, correo: cliente.correo, direccion_referencia: cliente.direccion_referencia,
    observaciones: cliente.observaciones, estado: cliente.estado,
  } : VACIO))
  const [error, setError] = useState('')
  const cambiar = (campo: keyof typeof VACIO) => (e: { target: { value: string } }) => setForm({ ...form, [campo]: e.target.value })

  async function guardar(e: FormEvent) {
    e.preventDefault()
    setError('')
    try {
      const r = cliente ? await api.patch<Cliente>(`clientes/${cliente.Code}/`, form) : await api.post<Cliente>('clientes/', form)
      alGuardar(r.data)
    } catch (err) {
      setError(mensajeDeError(err))
    }
  }

  return (
    <Modal titulo={cliente ? `Cliente ${cliente.Code}` : 'Nuevo cliente'} alCerrar={alCerrar}>
      <form onSubmit={guardar} className="space-y-4">
        <Aviso tipo="error">{error}</Aviso>
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo etiqueta="Nombre completo o razón social" ancho><input className="campo" value={form.nombre} onChange={cambiar('nombre')} /></Campo>
          <Campo etiqueta="Código">
            <input className="campo uppercase" value={form.Code} onChange={cambiar('Code')} disabled={!!cliente} required maxLength={40} placeholder="Ej. C-0001" />
          </Campo>
          <Campo etiqueta="Tipo de persona">
            <select className="campo" value={form.tipo_persona} onChange={cambiar('tipo_persona')}>
              <option value="fisica">Persona física</option><option value="juridica">Persona jurídica</option>
            </select>
          </Campo>
          <Campo etiqueta="Documento o RUC"><input className="campo" value={form.documento} onChange={cambiar('documento')} /></Campo>
          <Campo etiqueta="Teléfono"><input className="campo" value={form.telefono} onChange={cambiar('telefono')} /></Campo>
          <Campo etiqueta="Correo" ancho><input type="email" className="campo" value={form.correo} onChange={cambiar('correo')} /></Campo>
          <Campo etiqueta="Dirección de referencia" ancho><input className="campo" value={form.direccion_referencia} onChange={cambiar('direccion_referencia')} /></Campo>
          <Campo etiqueta="Observaciones" ancho><textarea className="campo" value={form.observaciones} onChange={cambiar('observaciones')} /></Campo>
          {cliente && (
            <Campo etiqueta="Estado">
              <select className="campo" value={form.estado} onChange={cambiar('estado')}>
                <option value="activo">Activo</option><option value="inactivo">Inactivo</option><option value="archivado">Archivado</option>
              </select>
            </Campo>
          )}
        </div>
        {cliente && <p className="text-xs text-koape-gris">Para archivar un cliente, antes hay que archivar sus conexiones.</p>}
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={!form.nombre.trim() || !form.Code.trim()}>Guardar</button>
        </div>
      </form>
    </Modal>
  )
}

function ConexionesDelCliente({ cliente, alCerrar }: { cliente: Cliente; alCerrar: () => void }) {
  const { api } = useSesion()
  const [conexiones, setConexiones] = useState<ConexionResumen[] | null>(null)
  useEffect(() => {
    api.get<ConexionResumen[]>(`clientes/${cliente.Code}/conexiones/`).then((r) => setConexiones(r.data)).catch(() => setConexiones([]))
  }, [api, cliente])
  return (
    <Modal titulo={`Conexiones de ${cliente.nombre}`} alCerrar={alCerrar}>
      {!conexiones ? <p className="text-sm text-koape-gris">Cargando…</p> : conexiones.length === 0 ? (
        <p className="text-sm text-koape-gris">No tiene conexiones.</p>
      ) : (
        <ul className="divide-y divide-koape-gris-claro/50 text-sm">
          {conexiones.map((c) => (
            <li key={c.Code} className="flex items-center justify-between py-2">
              <span><b>{c.Code}</b> · {c.direccion || 'sin dirección'} · {c.estado_nombre}</span>
              <Link className="font-semibold text-koape-rojo hover:underline" to={`/panel/conexiones/${c.Code}`}>Abrir</Link>
            </li>
          ))}
        </ul>
      )}
      <Link className="boton-primario mt-4" to={`/panel/nueva-conexion?cliente=${cliente.Code}`}>Nueva conexión para este cliente</Link>
    </Modal>
  )
}
