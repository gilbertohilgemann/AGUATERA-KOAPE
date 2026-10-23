import { useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { crearCliente, mensajeDeError } from '../api/cliente'
import type { DatosSesion } from '../api/tipos'
import { Aviso } from '../componentes/Aviso'
import { Logo } from '../componentes/Logo'
import { PieKoape } from '../componentes/PieKoape'
import { guardarToken } from '../sesion/almacen'

/** Ingreso: código institucional + usuario + contraseña. */
export function Ingreso() {
  const navegar = useNavigate()
  const [parametros] = useSearchParams()
  const api = useMemo(() => crearCliente(), [])
  const [codigo, setCodigo] = useState('')
  const [usuario, setUsuario] = useState('')
  const [contrasena, setContrasena] = useState('')
  const [sitioWeb, setSitioWeb] = useState('') // campo trampa anti-bots
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setError('')
    setEnviando(true)
    try {
      const { data } = await api.post<DatosSesion & { token: string }>('auth/ingresar/', {
        codigo_institucion: codigo,
        usuario,
        contrasena,
        sitio_web: sitioWeb,
      })
      guardarToken(data.token)
      navegar(data.usuario.debe_cambiar_contrasena ? '/panel/cuenta' : '/panel', { replace: true })
    } catch (err) {
      setError(mensajeDeError(err, 'No se pudo ingresar.'))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <aside className="relative hidden overflow-hidden bg-koape-tinta p-12 text-white lg:flex lg:flex-col lg:items-center lg:justify-center">
        <Logo claro grande />
        <div className="mt-14 text-center">
          <p className="font-titulo text-4xl font-extrabold leading-tight">
            Agua potable comunitaria,
            <br />
            <span className="bg-linear-to-r from-koape-magenta via-koape-rojo to-koape-amarillo bg-clip-text text-transparent">
              bien administrada.
            </span>
          </p>
          <p className="mx-auto mt-4 max-w-md text-sm text-koape-gris-claro">
            Padrón, lecturas, facturación, cobranzas y caja de aguateras y juntas de saneamiento.
          </p>
        </div>
        <div className="degradado-koape absolute inset-x-0 bottom-0 h-1.5" />
      </aside>

      <main className="flex flex-col p-6">
        <div className="grid flex-1 place-items-center">
          <form onSubmit={enviar} className="w-full max-w-sm space-y-4" noValidate>
            <div className="lg:hidden">
              <Logo />
            </div>
            <div>
              <h1 className="text-2xl font-extrabold">Ingresar</h1>
              <p className="text-sm text-koape-gris">Use el código de su institución, su usuario y su contraseña.</p>
            </div>
            <Aviso tipo="error">{error}</Aviso>
            {parametros.get('recuperada') && <Aviso tipo="exito">Contraseña guardada. Ingrese con la nueva.</Aviso>}
            <div>
              <label className="etiqueta" htmlFor="codigo">Código de institución</label>
              <input id="codigo" className="campo uppercase" value={codigo} onChange={(e) => setCodigo(e.target.value)}
                autoComplete="organization" autoCapitalize="characters" required />
            </div>
            <div>
              <label className="etiqueta" htmlFor="usuario">Usuario</label>
              <input id="usuario" className="campo" value={usuario} onChange={(e) => setUsuario(e.target.value)}
                autoComplete="username" autoCapitalize="none" required />
            </div>
            <div>
              <label className="etiqueta" htmlFor="contrasena">Contraseña</label>
              <input id="contrasena" type="password" className="campo" value={contrasena}
                onChange={(e) => setContrasena(e.target.value)} autoComplete="current-password" required />
            </div>
            {/* Honeypot: invisible para personas, los bots lo completan. */}
            <div aria-hidden="true" className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
              <label htmlFor="sitio_web">Sitio web</label>
              <input id="sitio_web" tabIndex={-1} autoComplete="off" value={sitioWeb} onChange={(e) => setSitioWeb(e.target.value)} />
            </div>
            <button className="boton-primario w-full" disabled={enviando || !codigo || !usuario || !contrasena}>
              {enviando ? 'Ingresando…' : 'Ingresar'}
            </button>
            <p className="text-sm">
              <Link className="text-koape-rojo hover:underline" to={`/recuperar?codigo=${encodeURIComponent(codigo)}&usuario=${encodeURIComponent(usuario)}`}>¿Olvidó su contraseña?</Link>
            </p>
            <p className="rounded-lg bg-koape-fondo p-3 text-sm">
              ¿Es usuario del servicio de agua? <Link className="font-semibold text-koape-rojo hover:underline" to="/portal">Consulte su cuenta aquí</Link>.
            </p>
          </form>
        </div>
        <PieKoape />
      </main>
    </div>
  )
}
