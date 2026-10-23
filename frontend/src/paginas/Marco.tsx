import { useState } from 'react'
import { Link, NavLink, Navigate, Outlet, useLocation } from 'react-router-dom'
import { urlArchivo } from '../api/configuracion'
import { Logo } from '../componentes/Logo'
import { useSesion } from '../sesion/ContextoSesion'

interface Item {
  ruta: string
  texto: string
  /** Alcanza con tener cualquiera de estos permisos para ver el ítem (el servidor vuelve a verificar). */
  permisos?: string[]
}

/**
 * Menú del panel (sección 20.1). Solo figuran los módulos ya construidos: cada fase agrega los suyos
 * (Clientes, Conexiones, Mapa, Lecturas, Facturación…). Nada de botones decorativos.
 */
export const GRUPOS: { grupo: string; items: Item[] }[] = [
  { grupo: 'General', items: [{ ruta: '', texto: 'Inicio' }] },
  {
    grupo: 'Padrón',
    items: [
      { ruta: 'clientes', texto: 'Clientes', permisos: ['padron.consultar', 'padron.clientes'] },
      { ruta: 'conexiones', texto: 'Conexiones', permisos: ['padron.consultar', 'padron.conexiones'] },
      { ruta: 'medidores', texto: 'Medidores', permisos: ['padron.consultar', 'padron.medidores'] },
      { ruta: 'zonas', texto: 'Zonas y barrios', permisos: ['territorio.gestionar', 'padron.consultar'] },
      { ruta: 'mapa', texto: 'Mapa', permisos: ['mapa.ver'] },
    ],
  },
  {
    grupo: 'Lecturas',
    items: [
      { ruta: 'recorridos', texto: 'Recorridos', permisos: ['recorridos.gestionar', 'lecturas.consultar'] },
      { ruta: 'lecturas', texto: 'Lecturas', permisos: ['lecturas.consultar', 'lecturas.revisar'] },
    ],
  },
  {
    grupo: 'Facturación',
    items: [
      { ruta: 'facturar', texto: 'Facturar (caja)', permisos: ['facturacion.emitir'] },
      { ruta: 'facturas', texto: 'Facturas', permisos: ['facturacion.consultar', 'facturacion.emitir', 'facturacion.anular'] },
    ],
  },
  {
    grupo: 'Cobranzas',
    items: [
      { ruta: 'cobrar', texto: 'Cobrar (crédito)', permisos: ['cobranzas.registrar'] },
      { ruta: 'recibos', texto: 'Recibos', permisos: ['cobranzas.consultar', 'cobranzas.registrar', 'cobranzas.anular'] },
      { ruta: 'cobros', texto: 'Historial de cobros', permisos: ['cobranzas.consultar', 'cobranzas.registrar', 'cobranzas.anular'] },
      { ruta: 'formas-pago', texto: 'Formas de pago', permisos: ['cobranzas.formas_pago'] },
    ],
  },
  {
    grupo: 'Caja y gastos',
    items: [
      { ruta: 'mi-caja', texto: 'Mi caja', permisos: ['caja.operar'] },
      { ruta: 'sesiones-caja', texto: 'Sesiones de caja', permisos: ['caja.operar', 'caja.supervisar'] },
      { ruta: 'gastos', texto: 'Gastos', permisos: ['gastos.registrar', 'gastos.consultar', 'gastos.confirmar'] },
      { ruta: 'cajas', texto: 'Cajas', permisos: ['caja.supervisar'] },
      { ruta: 'categorias-gasto', texto: 'Categorías de gastos', permisos: ['gastos.confirmar'] },
    ],
  },
  {
    grupo: 'Tarifas',
    items: [
      { ruta: 'tarifas', texto: 'Tarifas', permisos: ['tarifas.gestionar', 'liquidaciones.consultar'] },
      { ruta: 'liquidaciones', texto: 'Liquidaciones', permisos: ['liquidaciones.consultar', 'tarifas.gestionar'] },
    ],
  },
  {
    grupo: 'Informes',
    items: [
      { ruta: 'informes', texto: 'Informes y exportaciones', permisos: ['padron.consultar', 'lecturas.consultar', 'liquidaciones.consultar', 'facturacion.consultar', 'facturacion.emitir', 'cobranzas.consultar', 'gastos.consultar', 'gastos.confirmar', 'caja.supervisar'] },
    ],
  },
  {
    grupo: 'Administración',
    items: [
      { ruta: 'institucion', texto: 'Institución', permisos: ['institucion.ver', 'institucion.editar'] },
      { ruta: 'puntos-expedicion', texto: 'Puntos de expedición', permisos: ['institucion.ver', 'facturacion.numeracion'] },
      { ruta: 'usuarios', texto: 'Usuarios', permisos: ['usuarios.administrar'] },
      { ruta: 'roles', texto: 'Roles y permisos', permisos: ['roles.administrar'] },
      { ruta: 'auditoria', texto: 'Auditoría', permisos: ['auditoria.consultar'] },
      { ruta: 'integraciones', texto: 'Integraciones (API)', permisos: ['integraciones.administrar'] },
    ],
  },
  {
    grupo: 'Ayuda',
    items: [
      { ruta: 'manual', texto: 'Manual de usuario' },
      { ruta: 'cuenta', texto: 'Mi cuenta' },
    ],
  },
]

export function Marco() {
  const { datos, puede, salir } = useSesion()
  const ubicacion = useLocation()
  const [abierto, setAbierto] = useState(false)

  // Con la contraseña inicial o restablecida solo se puede cambiarla (el servidor también lo exige).
  if (datos.usuario.debe_cambiar_contrasena && !ubicacion.pathname.endsWith('/cuenta')) {
    return <Navigate to="/panel/cuenta" replace />
  }
  // Quien solo toma lecturas va directo a la aplicación del cobrador.
  if (ubicacion.pathname.replace(/\/$/, '') === '/panel' && datos.permisos.length > 0
      && datos.permisos.every((p) => p === 'lecturas.registrar')) {
    return <Navigate to="/cobrador" replace />
  }

  const visibles = GRUPOS.map((g) => ({
    ...g,
    items: g.items.filter((i) => !i.permisos || i.permisos.some((p) => puede(p))),
  })).filter((g) => g.items.length > 0)

  const menu = (
    <nav className="space-y-5">
      {visibles.map((g) => (
        <div key={g.grupo}>
          <p className="mb-1 px-3 text-[11px] font-semibold tracking-wider text-koape-gris uppercase">{g.grupo}</p>
          {g.items.map((i) => (
            <NavLink key={i.ruta} to={i.ruta ? `/panel/${i.ruta}` : '/panel'} end={!i.ruta}
              onClick={() => setAbierto(false)}
              className={({ isActive }) =>
                `block rounded-lg px-3 py-2 text-sm ${isActive ? 'bg-koape-rojo text-white' : 'text-koape-gris-claro hover:bg-white/10 hover:text-white'}`
              }>
              {i.texto}
            </NavLink>
          ))}
        </div>
      ))}
      {puede('lecturas.registrar') && (
        <Link to="/cobrador" className="block rounded-lg border border-white/20 px-3 py-2 text-sm font-semibold text-white hover:bg-white/10">
          📱 Aplicación del cobrador
        </Link>
      )}
    </nav>
  )

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[260px_1fr]">
      <aside className={`${abierto ? 'fixed inset-0 z-40 block' : 'hidden'} overflow-y-auto bg-koape-tinta p-4 lg:static lg:block`}>
        <div className="mb-6 flex items-center justify-between">
          <Logo claro compacto />
          <button className="text-2xl text-white lg:hidden" onClick={() => setAbierto(false)} aria-label="Cerrar menú">×</button>
        </div>
        {menu}
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-koape-gris-claro/70 bg-white px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <button className="boton-secundario lg:hidden" onClick={() => setAbierto(true)} aria-label="Abrir menú">☰</button>
            {datos.institucion.logo && <img src={urlArchivo(datos.institucion.logo)} alt="" className="h-8 w-auto" />}
            <div className="min-w-0">
              <p className="truncate font-titulo font-bold">{datos.institucion.nombre}</p>
              <p className="text-xs text-koape-gris">{datos.institucion.codigo}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden text-sm text-koape-gris sm:inline">
              {datos.usuario.nombre || datos.usuario.usuario}
            </span>
            <button className="boton-secundario" onClick={() => void salir()}>Salir</button>
          </div>
        </header>
        <div className="degradado-koape h-1" />
        <main className="flex-1 p-4 sm:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
