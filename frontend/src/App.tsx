import { BrowserRouter, Link, Navigate, Route, Routes } from 'react-router-dom'
import { leerToken } from './sesion/almacen'
import { AppCobrador } from './cobrador/AppCobrador'
import { ProveedorSesion } from './sesion/ContextoSesion'
import { Auditoria } from './paginas/Auditoria'
import { Ingreso } from './paginas/Ingreso'
import { Inicio } from './paginas/Inicio'
import { InstitucionPagina } from './paginas/InstitucionPagina'
import { Recuperar } from './paginas/Recuperar'
import { Manual } from './paginas/Manual'
import { Marco } from './paginas/Marco'
import { MiCuenta } from './paginas/MiCuenta'
import { PuntosExpedicion } from './paginas/PuntosExpedicion'
import { Roles } from './paginas/Roles'
import { Usuarios } from './paginas/Usuarios'
import { Clientes } from './paginas/padron/Clientes'
import { Conexiones } from './paginas/padron/Conexiones'
import { FichaConexion, NuevaConexion } from './paginas/padron/FichaConexion'
import { Mapa } from './paginas/padron/Mapa'
import { Medidores } from './paginas/padron/Medidores'
import { ZonasBarrios } from './paginas/padron/ZonasBarrios'
import { FichaLectura, Lecturas } from './paginas/lecturas/Lecturas'
import { FichaRecorrido, Recorridos } from './paginas/lecturas/Recorridos'
import { FichaLiquidacion, Liquidaciones } from './paginas/tarifas/Liquidaciones'
import { Tarifas } from './paginas/tarifas/Tarifas'
import { Facturar, Facturas, FichaFactura } from './paginas/facturacion/Facturas'
import { Cobrar, FichaRecibo, FormasPago, HistorialCobros, Recibos } from './paginas/cobranzas/Cobranzas'
import { Informes, Integraciones } from './paginas/informes/Informes'
import { AppPortal } from './portal/Portal'
import { Cajas, CategoriasGasto, FichaGasto, FichaSesion, Gastos, MiCajaPagina, SesionesCaja } from './paginas/caja/Caja'

function NoEncontrada() {
  return (
    <div className="grid min-h-[50vh] place-items-center text-center">
      <div>
        <p className="font-titulo text-3xl font-extrabold">Página no encontrada</p>
        <Link to="/" className="mt-4 inline-block text-koape-rojo hover:underline">Volver al inicio</Link>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to={leerToken() ? '/panel' : '/ingresar'} replace />} />
        <Route path="/ingresar" element={<Ingreso />} />
        <Route path="/recuperar" element={<Recuperar />} />
        <Route path="/cobrador/*" element={<AppCobrador />} />
        <Route path="/portal/*" element={<AppPortal />} />
        <Route path="/panel" element={<ProveedorSesion><Marco /></ProveedorSesion>}>
          <Route index element={<Inicio />} />
          <Route path="cuenta" element={<MiCuenta />} />
          <Route path="institucion" element={<InstitucionPagina />} />
          <Route path="puntos-expedicion" element={<PuntosExpedicion />} />
          <Route path="usuarios" element={<Usuarios />} />
          <Route path="roles" element={<Roles />} />
          <Route path="auditoria" element={<Auditoria />} />
          <Route path="manual" element={<Manual />} />
          <Route path="clientes" element={<Clientes />} />
          <Route path="conexiones" element={<Conexiones />} />
          <Route path="nueva-conexion" element={<NuevaConexion />} />
          <Route path="conexiones/:code" element={<FichaConexion />} />
          <Route path="medidores" element={<Medidores />} />
          <Route path="zonas" element={<ZonasBarrios />} />
          <Route path="mapa" element={<Mapa />} />
          <Route path="recorridos" element={<Recorridos />} />
          <Route path="recorridos/:code" element={<FichaRecorrido />} />
          <Route path="lecturas" element={<Lecturas />} />
          <Route path="lecturas/:comprobante" element={<FichaLectura />} />
          <Route path="tarifas" element={<Tarifas />} />
          <Route path="facturar" element={<Facturar />} />
          <Route path="facturas" element={<Facturas />} />
          <Route path="facturas/:referencia" element={<FichaFactura />} />
          <Route path="cobrar" element={<Cobrar />} />
          <Route path="recibos" element={<Recibos />} />
          <Route path="recibos/:numero" element={<FichaRecibo />} />
          <Route path="cobros" element={<HistorialCobros />} />
          <Route path="formas-pago" element={<FormasPago />} />
          <Route path="mi-caja" element={<MiCajaPagina />} />
          <Route path="sesiones-caja" element={<SesionesCaja />} />
          <Route path="sesiones-caja/:referencia" element={<FichaSesion />} />
          <Route path="cajas" element={<Cajas />} />
          <Route path="gastos" element={<Gastos />} />
          <Route path="gastos/:referencia" element={<FichaGasto />} />
          <Route path="categorias-gasto" element={<CategoriasGasto />} />
          <Route path="informes" element={<Informes />} />
          <Route path="integraciones" element={<Integraciones />} />
          <Route path="liquidaciones" element={<Liquidaciones />} />
          <Route path="liquidaciones/:numero" element={<FichaLiquidacion />} />
          <Route path="*" element={<NoEncontrada />} />
        </Route>
        <Route path="*" element={<NoEncontrada />} />
      </Routes>
    </BrowserRouter>
  )
}
