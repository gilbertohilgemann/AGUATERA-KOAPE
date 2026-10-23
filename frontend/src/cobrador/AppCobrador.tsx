import { Link, Route, Routes } from 'react-router-dom'
import { ProveedorSesion, useSesion } from '../sesion/ContextoSesion'
import { ProveedorCobrador } from './ContextoCobrador'
import { InicioCobrador, LecturasCobrador, MarcoCobrador, RecorridoCobrador } from './Paginas'
import { TomarLectura } from './TomarLectura'

function SoloCobradores() {
  const { puede } = useSesion()
  if (!puede('lecturas.registrar')) {
    return (
      <div className="grid min-h-screen place-items-center p-6 text-center">
        <div>
          <p className="text-lg font-bold">Su usuario no tiene el permiso para tomar lecturas.</p>
          <Link className="mt-3 inline-block text-koape-rojo underline" to="/panel">Ir al panel</Link>
        </div>
      </div>
    )
  }
  return (
    <ProveedorCobrador>
      <Routes>
        <Route element={<MarcoCobrador />}>
          <Route index element={<InicioCobrador />} />
          <Route path="r/:code" element={<RecorridoCobrador />} />
          <Route path="r/:code/leer" element={<TomarLectura />} />
          <Route path="enviadas" element={<LecturasCobrador />} />
          <Route path="*" element={<InicioCobrador />} />
        </Route>
      </Routes>
    </ProveedorCobrador>
  )
}

/** Aplicación del cobrador (PWA): trabaja sin conexión y sincroniza sin duplicar. */
export function AppCobrador() {
  return (
    <ProveedorSesion trabajaSinConexion>
      <SoloCobradores />
    </ProveedorSesion>
  )
}
