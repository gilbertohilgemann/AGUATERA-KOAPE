import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { mensajeDeError } from '../api/cliente'
import type { Permiso, Rol } from '../api/tipos'
import { Aviso } from '../componentes/Aviso'
import { Campo } from '../componentes/Campo'
import { Encabezado } from '../componentes/Encabezado'
import { Modal } from '../componentes/Modal'
import { useSesion } from '../sesion/ContextoSesion'

export function Roles() {
  const { api } = useSesion()
  const [roles, setRoles] = useState<Rol[]>([])
  const [permisos, setPermisos] = useState<Permiso[]>([])
  const [error, setError] = useState('')
  const [editando, setEditando] = useState<Rol | 'nuevo' | null>(null)

  const cargar = useCallback(async () => {
    try {
      const [r, p] = await Promise.all([api.get<Rol[]>('roles/'), api.get<Permiso[]>('permisos/')])
      setRoles(r.data)
      setPermisos(p.data)
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }, [api])

  useEffect(() => {
    void cargar()
  }, [cargar])

  return (
    <div>
      <Encabezado titulo="Roles y permisos"
        descripcion="Cada rol combina permisos. Los administradores institucionales tienen todos. Los roles no se borran: se desactivan."
        acciones={<button className="boton-primario" onClick={() => setEditando('nuevo')}>Nuevo rol</button>} />
      <Aviso tipo="error">{error}</Aviso>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {roles.map((r) => (
          <div key={r.id} className={`tarjeta p-5 ${r.activo ? '' : 'opacity-60'}`}>
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-titulo text-lg font-bold">{r.nombre} <span className="text-sm font-normal text-koape-gris">{r.Code}</span></p>
                <p className="text-xs text-koape-gris">{r.cantidad_usuarios} usuario(s) activo(s){r.activo ? '' : ' · desactivado'}</p>
              </div>
              <button className="text-sm font-semibold text-koape-rojo hover:underline" onClick={() => setEditando(r)}>Editar</button>
            </div>
            {r.descripcion && <p className="mt-2 text-sm">{r.descripcion}</p>}
            <ul className="mt-3 space-y-1 text-xs text-koape-gris">
              {r.permisos.length === 0 && <li>Sin permisos todavía.</li>}
              {r.permisos.map((c) => <li key={c}>• {permisos.find((p) => p.codigo === c)?.descripcion ?? c}</li>)}
            </ul>
          </div>
        ))}
      </div>
      {editando && (
        <FormularioRol rol={editando === 'nuevo' ? null : editando} permisos={permisos}
          alCerrar={() => setEditando(null)} alGuardar={() => { setEditando(null); void cargar() }} />
      )}
    </div>
  )
}

function FormularioRol({ rol, permisos, alCerrar, alGuardar }: { rol: Rol | null; permisos: Permiso[]; alCerrar: () => void; alGuardar: () => void }) {
  const { api } = useSesion()
  const [code, setCode] = useState(rol?.Code ?? '')
  const [nombre, setNombre] = useState(rol?.nombre ?? '')
  const [descripcion, setDescripcion] = useState(rol?.descripcion ?? '')
  const [activo, setActivo] = useState(rol?.activo ?? true)
  const [elegidos, setElegidos] = useState<string[]>(rol?.permisos ?? [])
  const [error, setError] = useState('')
  const [guardando, setGuardando] = useState(false)

  const porModulo = useMemo(() => {
    const grupos = new Map<string, Permiso[]>()
    for (const p of permisos) grupos.set(p.modulo, [...(grupos.get(p.modulo) ?? []), p])
    return [...grupos.entries()]
  }, [permisos])

  async function guardar(e: FormEvent) {
    e.preventDefault()
    setError('')
    setGuardando(true)
    const cuerpo = { Code: code, nombre, descripcion, activo, permisos: elegidos }
    try {
      if (rol) await api.patch(`roles/${rol.id}/`, cuerpo)
      else await api.post('roles/', cuerpo)
      alGuardar()
    } catch (err) {
      setError(mensajeDeError(err))
    } finally {
      setGuardando(false)
    }
  }

  const alternar = (codigo: string) =>
    setElegidos(elegidos.includes(codigo) ? elegidos.filter((c) => c !== codigo) : [...elegidos, codigo])

  return (
    <Modal titulo={rol ? `Editar rol ${rol.nombre}` : 'Nuevo rol'} alCerrar={alCerrar} amplio>
      <form onSubmit={guardar} className="space-y-4">
        <Aviso tipo="error">{error}</Aviso>
        <div className="grid gap-4 sm:grid-cols-2">
          <Campo etiqueta="Código">
            <input className="campo uppercase" required maxLength={40} disabled={!!rol} value={code} onChange={(e) => setCode(e.target.value)} placeholder="Ej. CAJERO" />
          </Campo>
          <Campo etiqueta="Nombre">
            <input className="campo" value={nombre} onChange={(e) => setNombre(e.target.value)} />
          </Campo>
          <Campo etiqueta="Descripción">
            <input className="campo" value={descripcion} onChange={(e) => setDescripcion(e.target.value)} />
          </Campo>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={activo} onChange={(e) => setActivo(e.target.checked)} /> Activo
        </label>
        {porModulo.map(([modulo, lista]) => (
          <fieldset key={modulo}>
            <legend className="etiqueta">{modulo}</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {lista.map((p) => (
                <label key={p.codigo} className="flex items-start gap-2 rounded-lg border border-koape-gris-claro p-2 text-sm">
                  <input type="checkbox" className="mt-1" checked={elegidos.includes(p.codigo)} onChange={() => alternar(p.codigo)} />
                  {p.descripcion}
                </label>
              ))}
            </div>
          </fieldset>
        ))}
        <div className="flex justify-end gap-2">
          <button type="button" className="boton-secundario" onClick={alCerrar}>Cancelar</button>
          <button className="boton-primario" disabled={guardando || !nombre.trim() || !code.trim()}>{guardando ? 'Guardando…' : 'Guardar'}</button>
        </div>
      </form>
    </Modal>
  )
}
