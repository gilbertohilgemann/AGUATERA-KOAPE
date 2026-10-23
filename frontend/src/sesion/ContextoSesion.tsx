import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { AxiosInstance } from 'axios'
import { useNavigate } from 'react-router-dom'
import { crearCliente } from '../api/cliente'
import type { DatosSesion } from '../api/tipos'
import axios from 'axios'
import { borrarToken, guardarDatosSesion, leerDatosSesion, leerToken, recordarEnEsteEquipo } from './almacen'

interface ValorSesion {
  api: AxiosInstance
  datos: DatosSesion
  refrescar: () => Promise<void>
  salir: () => Promise<void>
  /** Solo para mostrar u ocultar opciones: el servidor vuelve a verificar cada permiso. */
  puede: (permiso: string) => boolean
  /** La sesión se abrió con la copia guardada en el teléfono porque no hay conexión (modo cobrador). */
  sinConexion: boolean
}

const Contexto = createContext<ValorSesion | null>(null)

export function useSesion(): ValorSesion {
  const valor = useContext(Contexto)
  if (!valor) throw new Error('useSesion debe usarse dentro de <ProveedorSesion>')
  return valor
}

/**
 * Carga la sesión; sin token válido vuelve al ingreso.
 * `trabajaSinConexion` (aplicación del cobrador): recuerda la sesión en el teléfono y, si no hay conexión,
 * abre con la última copia de los datos de sesión mientras no haya vencido.
 */
export function ProveedorSesion({ children, trabajaSinConexion = false }: { children: ReactNode; trabajaSinConexion?: boolean }) {
  const navegar = useNavigate()
  // `useNavigate` cambia en cada navegación: el cliente de la API se crea UNA vez y usa la última versión.
  const navegarRef = useRef(navegar)
  navegarRef.current = navegar
  const api = useMemo(() => crearCliente(() => navegarRef.current('/ingresar', { replace: true })), [])
  const [datos, setDatos] = useState<DatosSesion | null>(null)
  const [error, setError] = useState('')
  const [sinConexion, setSinConexion] = useState(false)

  const refrescar = useCallback(async () => {
    try {
      const respuesta = await api.get<DatosSesion>('auth/yo/')
      setDatos(respuesta.data)
      setSinConexion(false)
      if (trabajaSinConexion) {
        recordarEnEsteEquipo()
        guardarDatosSesion(respuesta.data)
      }
    } catch (e) {
      const copia = trabajaSinConexion ? leerDatosSesion<DatosSesion>() : null
      // Sin red o con el servidor caído (5xx): se trabaja con la copia del teléfono.
      const sinRed = axios.isAxiosError(e) && (!e.response || e.response.status >= 500)
      if (sinRed && copia && new Date(copia.sesion_vence_en).getTime() > Date.now()) {
        setDatos(copia)
        setSinConexion(true)
        return
      }
      throw e
    }
  }, [api, trabajaSinConexion])

  const cargar = useCallback(() => {
    if (!leerToken()) {
      navegarRef.current('/ingresar', { replace: true })
      return
    }
    setError('')
    refrescar().catch(() => setError('No se pudo cargar la sesión.'))
  }, [refrescar])

  useEffect(cargar, [cargar])

  const salir = useCallback(async () => {
    try {
      await api.post('auth/salir/')
    } catch {
      /* aunque falle, se cierra localmente */
    }
    borrarToken()
    navegarRef.current('/ingresar', { replace: true })
  }, [api])

  const valor = useMemo<ValorSesion | null>(() => (datos ? {
    api, datos, refrescar, salir, sinConexion,
    puede: (permiso: string) => datos.permisos.includes(permiso),
  } : null), [api, datos, refrescar, salir, sinConexion])

  if (error) {
    return (
      <div className="grid min-h-screen place-items-center p-8 text-center">
        <div>
          <p className="text-koape-rojo">{error}</p>
          <button className="boton-secundario mt-4" onClick={cargar}>Reintentar</button>
        </div>
      </div>
    )
  }
  if (!valor) return <div className="grid min-h-screen place-items-center text-koape-gris">Cargando…</div>
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>
}
