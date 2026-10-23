import { useState, type FormEvent } from 'react'
import { mensajeDeError } from '../api/cliente'
import { Aviso } from '../componentes/Aviso'
import { Campo } from '../componentes/Campo'
import { Encabezado } from '../componentes/Encabezado'
import { useSesion } from '../sesion/ContextoSesion'

export function MiCuenta() {
  const { api, datos, refrescar } = useSesion()
  const [actual, setActual] = useState('')
  const [nueva, setNueva] = useState('')
  const [repetir, setRepetir] = useState('')
  const [error, setError] = useState('')
  const [exito, setExito] = useState('')
  const [enviando, setEnviando] = useState(false)

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setError('')
    setExito('')
    if (nueva !== repetir) {
      setError('Las contraseñas nuevas no coinciden.')
      return
    }
    setEnviando(true)
    try {
      await api.post('auth/cambiar-contrasena/', { contrasena_actual: actual, contrasena_nueva: nueva })
      setActual('')
      setNueva('')
      setRepetir('')
      setExito('Contraseña actualizada. Se cerraron sus otras sesiones abiertas.')
      await refrescar()
    } catch (err) {
      setError(mensajeDeError(err))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="max-w-xl">
      <Encabezado titulo="Mi cuenta" descripcion={`${datos.usuario.usuario} · ${datos.institucion.codigo}`} />
      {datos.usuario.debe_cambiar_contrasena && (
        <div className="mb-4">
          <Aviso tipo="info">Por seguridad, cambie su contraseña inicial antes de continuar.</Aviso>
        </div>
      )}
      <form onSubmit={enviar} className="tarjeta space-y-4 p-6">
        <h2 className="text-lg font-bold">Cambiar contraseña</h2>
        <Aviso tipo="error">{error}</Aviso>
        <Aviso tipo="exito">{exito}</Aviso>
        <Campo etiqueta="Contraseña actual">
          <input type="password" className="campo" value={actual} onChange={(e) => setActual(e.target.value)} autoComplete="current-password" />
        </Campo>
        <Campo etiqueta="Contraseña nueva">
          <input type="password" className="campo" value={nueva} onChange={(e) => setNueva(e.target.value)} autoComplete="new-password" />
        </Campo>
        <Campo etiqueta="Repetir la contraseña nueva">
          <input type="password" className="campo" value={repetir} onChange={(e) => setRepetir(e.target.value)} autoComplete="new-password" />
        </Campo>
        <p className="text-xs text-koape-gris">Al menos 8 caracteres; que no sea solo números ni una contraseña común.</p>
        <button className="boton-primario" disabled={enviando || !actual || !nueva || !repetir}>
          {enviando ? 'Guardando…' : 'Cambiar contraseña'}
        </button>
      </form>
    </div>
  )
}
