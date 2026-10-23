import { useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { crearCliente, mensajeDeError } from '../api/cliente'
import { Aviso } from '../componentes/Aviso'
import { Logo } from '../componentes/Logo'
import { PieKoape } from '../componentes/PieKoape'

/**
 * «Olvidé mi contraseña» del personal (D51): 1) código de institución + usuario → llega un código de 6 dígitos al
 * correo cargado en su usuario; 2) código + contraseña nueva. Sin correo cargado, la restablece un administrador.
 */
export function Recuperar() {
  const navegar = useNavigate()
  const [parametros] = useSearchParams()
  const api = useMemo(() => crearCliente(), [])
  const [paso, setPaso] = useState<'pedir' | 'confirmar'>('pedir')
  const [codigoInstitucion, setCodigoInstitucion] = useState(parametros.get('codigo') ?? '')
  const [usuario, setUsuario] = useState(parametros.get('usuario') ?? '')
  const [codigo, setCodigo] = useState('')
  const [nueva, setNueva] = useState('')
  const [repetir, setRepetir] = useState('')
  const [aviso, setAviso] = useState('')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  async function pedir(e: FormEvent) {
    e.preventDefault()
    setError('')
    setEnviando(true)
    try {
      const r = await api.post<{ detalle: string }>('auth/recuperar/', { codigo_institucion: codigoInstitucion, usuario })
      setAviso(r.data.detalle)
      setPaso('confirmar')
    } catch (err) { setError(mensajeDeError(err)) } finally { setEnviando(false) }
  }

  async function confirmar(e: FormEvent) {
    e.preventDefault()
    setError('')
    if (nueva !== repetir) { setError('Las dos contraseñas no coinciden.'); return }
    setEnviando(true)
    try {
      await api.post('auth/recuperar/confirmar/', { codigo_institucion: codigoInstitucion, usuario, codigo: codigo.trim(), contrasena_nueva: nueva })
      navegar('/ingresar?recuperada=1', { replace: true })
    } catch (err) { setError(mensajeDeError(err)) } finally { setEnviando(false) }
  }

  return (
    <div className="flex min-h-screen flex-col p-6">
      <div className="grid flex-1 place-items-center">
        <div className="w-full max-w-sm space-y-4">
          <Logo />
          <div>
            <h1 className="text-2xl font-extrabold">Olvidé mi contraseña</h1>
            <p className="text-sm text-koape-gris">Le enviamos un código al correo cargado en su usuario.</p>
          </div>
          <Aviso tipo="error">{error}</Aviso>
          <Aviso tipo="exito">{aviso}</Aviso>
          {paso === 'pedir' ? (
            <form onSubmit={pedir} className="space-y-4">
              <div>
                <label className="etiqueta" htmlFor="codigo_institucion">Código de institución</label>
                <input id="codigo_institucion" className="campo uppercase" value={codigoInstitucion} onChange={(e) => setCodigoInstitucion(e.target.value)} autoCapitalize="characters" required />
              </div>
              <div>
                <label className="etiqueta" htmlFor="usuario">Usuario</label>
                <input id="usuario" className="campo" value={usuario} onChange={(e) => setUsuario(e.target.value)} autoCapitalize="none" autoComplete="username" required />
              </div>
              <button className="boton-primario w-full" disabled={enviando || !codigoInstitucion.trim() || !usuario.trim()}>{enviando ? 'Enviando…' : 'Enviarme el código'}</button>
            </form>
          ) : (
            <form onSubmit={confirmar} className="space-y-4">
              <div>
                <label className="etiqueta" htmlFor="codigo">Código recibido (6 dígitos)</label>
                <input id="codigo" className="campo text-center text-xl tracking-widest" inputMode="numeric" maxLength={6} value={codigo} onChange={(e) => setCodigo(e.target.value.replace(/\D/g, ''))} autoComplete="one-time-code" required />
              </div>
              <div>
                <label className="etiqueta" htmlFor="nueva">Contraseña nueva</label>
                <input id="nueva" type="password" className="campo" value={nueva} onChange={(e) => setNueva(e.target.value)} autoComplete="new-password" required />
              </div>
              <div>
                <label className="etiqueta" htmlFor="repetir">Repítala</label>
                <input id="repetir" type="password" className="campo" value={repetir} onChange={(e) => setRepetir(e.target.value)} autoComplete="new-password" required />
              </div>
              <button className="boton-primario w-full" disabled={enviando || codigo.length !== 6 || !nueva || !repetir}>{enviando ? 'Guardando…' : 'Guardar contraseña'}</button>
              <button type="button" className="w-full text-sm text-koape-gris hover:underline" onClick={() => { setPaso('pedir'); setAviso('') }}>Pedir otro código</button>
            </form>
          )}
          <p className="text-xs text-koape-gris">Si su usuario no tiene un correo cargado, pídale al administrador de su institución que le restablezca la contraseña.</p>
          <p className="text-center text-sm"><Link className="text-koape-rojo hover:underline" to="/ingresar">← Volver a ingresar</Link></p>
        </div>
      </div>
      <PieKoape />
    </div>
  )
}
