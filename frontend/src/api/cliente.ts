import axios, { AxiosError, type AxiosInstance } from 'axios'
import { borrarToken, leerToken } from '../sesion/almacen'
import { nuevoIdentificador } from '../utilidades/identificador'
import { urlApi } from './configuracion'

/**
 * Cliente axios de la API. La institución NUNCA viaja en el pedido: el servidor la toma del token.
 */
export function crearCliente(alExpirar?: () => void): AxiosInstance {
  const cliente = axios.create({ baseURL: urlApi(), timeout: 60_000 })
  cliente.interceptors.request.use((config) => {
    const token = leerToken()
    if (token) config.headers.set('Authorization', `Token ${token}`)
    config.headers.set('X-Id-Solicitud', nuevoIdentificador())
    return config
  })
  cliente.interceptors.response.use(
    (r) => r,
    (error: AxiosError) => {
      const url = error.config?.url ?? ''
      if (error.response?.status === 401 && !url.includes('auth/ingresar')) {
        borrarToken()
        alExpirar?.()
      }
      return Promise.reject(error)
    },
  )
  return cliente
}

/** Mensaje legible a partir de un error de la API (formato `{detalle}` o errores por campo). */
export function mensajeDeError(error: unknown, porDefecto = 'No se pudo completar la operación.'): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) return 'No hay conexión con el servidor. Verifique que el sistema esté en marcha.'
    if (error.response.status === 429) return 'Demasiados intentos. Espere un minuto y vuelva a probar.'
    const datos = error.response.data as unknown
    if (datos && typeof datos === 'object') {
      const registro = datos as Record<string, unknown>
      if (typeof registro.detalle === 'string') return registro.detalle
      const partes: string[] = []
      for (const [campo, valor] of Object.entries(registro)) {
        const texto = Array.isArray(valor) ? valor.join(' ') : typeof valor === 'string' ? valor : ''
        if (texto) partes.push(campo === 'non_field_errors' ? texto : `${campo}: ${texto}`)
      }
      if (partes.length) return partes.join(' · ')
    }
    if (error.response.status === 403) return 'No tiene permiso para realizar esta acción.'
  }
  return porDefecto
}
