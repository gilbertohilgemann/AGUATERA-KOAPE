import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { mensajeDeError } from '../api/cliente'
import type { Pagina, Rol, Usuario } from '../api/tipos'
import { Aviso } from '../componentes/Aviso'
import { Campo } from '../componentes/Campo'
import { Encabezado } from '../componentes/Encabezado'
import { Modal } from '../componentes/Modal'
import { useSesion } from '../sesion/ContextoSesion'
import { fechaHora } from '../utilidades/fechas'

interface Formulario {
  usuario: string
  nombre: string
  apellido: string
  correo: string
  activo: boolean
  es_admin_institucion: boolean
  roles: number[]
  contrasena: string
}

const VACIO: Formulario = { usuario: '', nombre: '', apellido: '', correo: '', activo: true, es_admin_institucion: false, roles: [], contrasena: '' }

export function Usuarios() {
  const { api, datos } = useSesion()
  const [usuarios, setUsuarios] = useState<Usuario[]>([])
  const [roles, setRoles] = useState<Rol[]>([])
  const [buscar, setBuscar] = useState('')
  const [error, setError] = useState('')
  const [editando, setEditando] = useState<Usuario | 'nuevo' | null>(null)
  const [restablecer, setRestablecer] = useState<Usuario | null>(null)

  const cargar = useCallback(async () => {
    try {
      const r = await api.get<Pagina<Usuario>>('usuarios/', { params: { buscar: buscar || undefined, tamanio: 200 } })
      setUsuarios(r.data.results)
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }, [api, buscar])

  useEffect(() => {
    void cargar()
  }, [cargar])

  useEffect(() => {
    api.get<Rol[]>('roles/').then((r) => setRoles(r.data)).catch(() => setRoles([]))
  }, [api])

  const nombreRol = (id: number) => roles.find((r) => r.id === id)?.nombre ?? "—"

  return (
    <div>
      <Encabezado titulo="Usuarios" descripcion="Los usuarios no se borran: se desactivan, así queda la trazabilidad."
        acciones={<button className="boton-primario" onClick={() => setEditando('nuevo')}>Nuevo usuario</button>} />
      <Aviso tipo="error">{error}</Aviso>
      <div className="mb-4 max-w-sm">
        <input className="campo" placeholder="Buscar por usuario, nombre o correo" value={buscar} onChange={(e) => setBuscar(e.target.value)} />
      </div>
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead>
            <tr><th>Usuario</th><th>Nombre</th><th>Roles</th><th>Estado</th><th>Último ingreso</th><th /></tr>
          </thead>
          <tbody>
            {usuarios.map((u) => (
              <tr key={u.id} className={u.activo ? '' : 'text-koape-gris'}>
                <td className="font-semibold">{u.usuario}</td>
                <td>{`${u.nombre} ${u.apellido}`.trim() || '—'}</td>
                <td>{u.es_admin_institucion ? 'Administrador' : u.roles.map(nombreRol).join(', ') || '—'}</td>
                <td>
                  {!u.activo ? 'Desactivado' : u.bloqueado ? 'Bloqueado temporalmente' : u.debe_cambiar_contrasena ? 'Debe cambiar contraseña' : 'Activo'}
                </td>
                <td>{fechaHora(u.ultimo_ingreso)}</td>
                <td className="whitespace-nowrap text-right">
                  <button className="text-sm font-semibold text-koape-rojo hover:underline" onClick={() => setEditando(u)}>Editar</button>
                  {u.id !== datos.usuario.id && (
                    <button className="ml-3 text-sm font-semibold text-koape-magenta hover:underline" onClick={() => setRestablecer(u)}>
                      Restablecer contraseña
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {usuarios.length === 0 && <tr><td colSpan={6} className="text-center text-koape-gris">Sin resultados.</td></tr>}
          </tbody>
        </table>
      </div>
      {editando && (
        <FormularioUsuario usuario={editando === 'nuevo' ? null : editando} roles={roles}
          alCerrar={() => setEditando(null)} alGuardar={() => { setEditando(null); void cargar() }} />
      )}
      {restablecer && <RestablecerContrasena usuario={restablecer} alCerrar={() => { setRestablecer(null); void cargar() }} />}
    </div>
  )
}

function FormularioUsuario({ usuario, roles, alCerrar, alGuardar }: { usuario: Usuario | null; roles: Rol[]; alCerrar: () => void; alGuardar: () => void }) {
  const { api, datos } = useSesion()
  const [form, setForm] = useState<Formulario>(() =>
    usuario
      ? {
          usuario: usuario.usuario, nombre: usuario.nombre, apellido: usuario.apellido, correo: usuario.correo,
          activo: usuario.activo, es_admin_institucion: usuario.es_admin_institucion, roles: usuario.roles, contrasena: '',
        }
      : VACIO,
  )
  const [error, setError] = useState('')
  const [guardando, setGuardando] = useState(false)
  const soyAdmin = datos.usuario.es_admin_institucion
  const activos = roles.filter((r) => r.activo)

  async function guardar(e: FormEvent) {
    e.preventDefault()
    setError('')
    setGuardando(true)
    const cuerpo: Partial<Formulario> = { ...form }
    if (usuario) delete cuerpo.contrasena
    try {
      if (usuario) await api.patch(`usuarios/${usuario.id}/`, cuerpo)
      else await api.post('usuarios/', cuerpo)
      alGuardar()
    } catch (err) {
      setError(mensajeDeError(err))
    } finally {
      setGuardando(false)
    }
  }

  const alternarRol = (id: number) =>
    setForm({ ...form, roles: form.roles.includes(id) ? form.roles.filter((r) => r !== id) : [...form.roles, id] })

  return (
    <Modal titulo={usuario ? `Editar ${usuario.usuario}` : 'Nuevo usuario'} alCerrar={alCerrar}>
      <form onSubmit={guardar} className="space-y-4">
        <Aviso tipo="error">{error}</Aviso>
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo etiqueta="Usuario">
            <input className="campo" value={form.usuario} disabled={!!usuario} onChange={(e) => setForm({ ...form, usuario: e.target.value })} autoCapitalize="none" />
          </Campo>
          {!usuario && (
            <Campo etiqueta="Contraseña inicial">
              <input type="password" className="campo" value={form.contrasena} onChange={(e) => setForm({ ...form, contrasena: e.target.value })} autoComplete="new-password" />
            </Campo>
          )}
          <Campo etiqueta="Nombre">
            <input className="campo" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} />
          </Campo>
          <Campo etiqueta="Apellido">
            <input className="campo" value={form.apellido} onChange={(e) => setForm({ ...form, apellido: e.target.value })} />
          </Campo>
          <Campo etiqueta="Correo" ancho>
            <input type="email" className="campo" value={form.correo} onChange={(e) => setForm({ ...form, correo: e.target.value })} />
          </Campo>
        </div>
        {!usuario && <p className="text-xs text-koape-gris">Al primer ingreso el sistema le pedirá cambiar la contraseña.</p>}
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.activo} onChange={(e) => setForm({ ...form, activo: e.target.checked })} /> Activo
        </label>
        {soyAdmin && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.es_admin_institucion} onChange={(e) => setForm({ ...form, es_admin_institucion: e.target.checked })} />
            Administrador institucional (todos los permisos)
          </label>
        )}
        {!form.es_admin_institucion && (
          <fieldset>
            <legend className="etiqueta">Roles</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {activos.map((r) => (
                <label key={r.id} className="flex items-start gap-2 rounded-lg border border-koape-gris-claro p-2 text-sm">
                  <input type="checkbox" className="mt-1" checked={form.roles.includes(r.id)} onChange={() => alternarRol(r.id)} />
                  <span><span className="font-semibold">{r.nombre}</span>{r.descripcion && <span className="block text-xs text-koape-gris">{r.descripcion}</span>}</span>
                </label>
              ))}
            </div>
          </fieldset>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={guardando}>{guardando ? 'Guardando…' : 'Guardar'}</button>
        </div>
      </form>
    </Modal>
  )
}

function RestablecerContrasena({ usuario, alCerrar }: { usuario: Usuario; alCerrar: () => void }) {
  const { api } = useSesion()
  const [contrasena, setContrasena] = useState('')
  const [error, setError] = useState('')
  const [exito, setExito] = useState('')

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setError('')
    try {
      const r = await api.post<{ detalle: string }>(`usuarios/${usuario.id}/restablecer-contrasena/`, { contrasena_nueva: contrasena })
      setExito(r.data.detalle)
    } catch (err) {
      setError(mensajeDeError(err))
    }
  }

  return (
    <Modal titulo={`Restablecer la contraseña de ${usuario.usuario}`} alCerrar={alCerrar}>
      <form onSubmit={enviar} className="space-y-4">
        <p className="text-sm text-koape-gris">Se cierran sus sesiones abiertas y deberá cambiarla al ingresar. Queda registrado en la auditoría.</p>
        <Aviso tipo="error">{error}</Aviso>
        <Aviso tipo="exito">{exito}</Aviso>
        {!exito && (
          <>
            <Campo etiqueta="Contraseña provisoria">
              <input type="password" className="campo" value={contrasena} onChange={(e) => setContrasena(e.target.value)} autoComplete="new-password" />
            </Campo>
            <button className="boton-primario" disabled={!contrasena}>Restablecer</button>
          </>
        )}
        {exito && <button type="button" className="boton-secundario" onClick={alCerrar}>Cerrar</button>}
      </form>
    </Modal>
  )
}
