import { useCallback, useEffect, useState } from 'react'
import { mensajeDeError } from '../api/cliente'
import type { Pagina, RegistroAuditoria } from '../api/tipos'
import { Aviso } from '../componentes/Aviso'
import { Campo } from '../componentes/Campo'
import { Encabezado } from '../componentes/Encabezado'
import { Modal } from '../componentes/Modal'
import { useSesion } from '../sesion/ContextoSesion'
import { fechaHora } from '../utilidades/fechas'

const ACCIONES: Record<string, string> = {
  ingreso: 'Ingreso', ingreso_fallido: 'Ingreso fallido', salida: 'Salida', cambio_contrasena: 'Cambio de contraseña',
  contrasena_restablecida: 'Contraseña restablecida', contrasena_restablecida_por_plataforma: 'Contraseña restablecida (plataforma)',
  usuario_creado: 'Usuario creado', usuario_modificado: 'Usuario modificado', rol_creado: 'Rol creado',
  rol_modificado: 'Rol modificado', institucion_creada: 'Institución creada', institucion_modificada: 'Institución modificada',
  institucion_estado: 'Cambio de estado de la institución',
}

export function Auditoria() {
  const { api } = useSesion()
  const [registros, setRegistros] = useState<RegistroAuditoria[]>([])
  const [total, setTotal] = useState(0)
  const [pagina, setPagina] = useState(1)
  const [filtros, setFiltros] = useState({ desde: '', hasta: '', accion: '', usuario: '', resultado: '' })
  const [error, setError] = useState('')
  const [detalle, setDetalle] = useState<RegistroAuditoria | null>(null)

  const cargar = useCallback(async () => {
    try {
      const params = Object.fromEntries(Object.entries({ ...filtros, pagina }).filter(([, v]) => v !== ''))
      const r = await api.get<Pagina<RegistroAuditoria>>('auditoria/', { params })
      setRegistros(r.data.results)
      setTotal(r.data.count)
    } catch (e) {
      setError(mensajeDeError(e))
    }
  }, [api, filtros, pagina])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const filtrar = (cambio: Partial<typeof filtros>) => {
    setPagina(1)
    setFiltros({ ...filtros, ...cambio })
  }
  const paginas = Math.max(1, Math.ceil(total / 50))

  return (
    <div>
      <Encabezado titulo="Auditoría" descripcion="Registro de solo lectura de las operaciones de la institución." />
      <Aviso tipo="error">{error}</Aviso>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Campo etiqueta="Desde"><input type="date" className="campo" value={filtros.desde} onChange={(e) => filtrar({ desde: e.target.value })} /></Campo>
        <Campo etiqueta="Hasta"><input type="date" className="campo" value={filtros.hasta} onChange={(e) => filtrar({ hasta: e.target.value })} /></Campo>
        <Campo etiqueta="Acción">
          <select className="campo" value={filtros.accion} onChange={(e) => filtrar({ accion: e.target.value })}>
            <option value="">Todas</option>
            {Object.entries(ACCIONES).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
        </Campo>
        <Campo etiqueta="Usuario"><input className="campo" value={filtros.usuario} onChange={(e) => filtrar({ usuario: e.target.value })} /></Campo>
        <Campo etiqueta="Resultado">
          <select className="campo" value={filtros.resultado} onChange={(e) => filtrar({ resultado: e.target.value })}>
            <option value="">Todos</option><option value="exito">Éxito</option><option value="fallo">Fallo</option>
          </select>
        </Campo>
      </div>
      <div className="tarjeta overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>Fecha y hora</th><th>Usuario</th><th>Acción</th><th>Entidad</th><th>Resultado</th><th>IP</th><th /></tr></thead>
          <tbody>
            {registros.map((r) => (
              <tr key={r.id}>
                <td className="whitespace-nowrap">{fechaHora(r.ocurrido_en)}</td>
                <td>{r.usuario_nombre || '—'}</td>
                <td>{ACCIONES[r.accion] ?? r.accion}</td>
                <td>{r.entidad ? `${r.entidad} ${r.entidad_id}` : '—'}</td>
                <td className={r.resultado === 'fallo' ? 'font-semibold text-koape-rojo' : ''}>{r.resultado === 'fallo' ? 'Fallo' : 'Éxito'}</td>
                <td>{r.ip ?? '—'}</td>
                <td className="text-right"><button className="text-sm font-semibold text-koape-rojo hover:underline" onClick={() => setDetalle(r)}>Ver</button></td>
              </tr>
            ))}
            {registros.length === 0 && <tr><td colSpan={7} className="text-center text-koape-gris">Sin registros.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex items-center justify-between text-sm text-koape-gris">
        <span>{total} registro(s)</span>
        <div className="flex items-center gap-2">
          <button className="boton-secundario" disabled={pagina <= 1} onClick={() => setPagina(pagina - 1)}>Anterior</button>
          <span>{pagina} / {paginas}</span>
          <button className="boton-secundario" disabled={pagina >= paginas} onClick={() => setPagina(pagina + 1)}>Siguiente</button>
        </div>
      </div>
      {detalle && (
        <Modal titulo={ACCIONES[detalle.accion] ?? detalle.accion} alCerrar={() => setDetalle(null)} amplio>
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div><dt className="etiqueta">Fecha y hora</dt><dd>{fechaHora(detalle.ocurrido_en)}</dd></div>
            <div><dt className="etiqueta">Usuario</dt><dd>{detalle.usuario_nombre || '—'}</dd></div>
            <div><dt className="etiqueta">IP</dt><dd>{detalle.ip ?? '—'}</dd></div>
            <div><dt className="etiqueta">ID de solicitud</dt><dd className="font-mono text-xs">{detalle.id_solicitud || '—'}</dd></div>
            {detalle.motivo && <div className="sm:col-span-2"><dt className="etiqueta">Motivo</dt><dd>{detalle.motivo}</dd></div>}
          </dl>
          {(['antes', 'despues', 'detalle'] as const).map((clave) => {
            const valor = detalle[clave]
            if (!valor || Object.keys(valor).length === 0) return null
            return (
              <div key={clave} className="mt-4">
                <p className="etiqueta">{clave === 'antes' ? 'Antes' : clave === 'despues' ? 'Después' : 'Detalle'}</p>
                <pre className="overflow-x-auto rounded-lg bg-koape-fondo p-3 text-xs">{JSON.stringify(valor, null, 2)}</pre>
              </div>
            )
          })}
        </Modal>
      )}
    </div>
  )
}
