import axios, { type AxiosInstance } from 'axios'
import type { DeudasLectura, Lectura } from '../api/tipos'
import { guardarOperacion, operacionesDe, type Operacion } from './almacenLocal'

/**
 * Envía al servidor las lecturas guardadas en el teléfono (sección 10.2).
 * - Una por una, en el orden en que se tomaron, con su `id_operacion`: si el envío se corta y se reintenta,
 *   el servidor devuelve la misma lectura (no la duplica).
 * - Recién cuando el servidor confirma la lectura CON su foto, se marca sincronizada y se borran las fotos
 *   del teléfono.
 * - Un rechazo del servidor (regla de negocio) queda como «Error» con el mensaje: no se reintenta solo.
 * - Sin conexión no pasa nada: queda pendiente para el próximo intento.
 */

let enCurso: Promise<ResultadoSincronizacion> | null = null

export interface ResultadoSincronizacion {
  enviadas: number
  errores: number
  sinConexion: boolean
  sesionVencida: boolean
}

function formulario(op: Operacion): FormData {
  const datos = new FormData()
  datos.append('id_operacion', op.id_operacion)
  datos.append('recorrido', op.recorrido)
  datos.append('medidor', op.medidor)
  datos.append('lectura_actual', op.lectura_actual)
  datos.append('capturada_en', op.capturada_en)
  datos.append('latitud', op.latitud.toFixed(6))
  datos.append('longitud', op.longitud.toFixed(6))
  if (op.precision_metros !== null) datos.append('precision_metros', String(Math.round(op.precision_metros)))
  datos.append('comentario', op.comentario)
  datos.append('foto_origen', op.foto_origen)
  if (op.foto) datos.append('foto', op.foto, 'medidor.jpg')
  op.adicionales.forEach((f, n) => datos.append('adicionales', f, `adicional-${n + 1}.jpg`))
  return datos
}

export async function enviarOperacion(api: AxiosInstance, op: Operacion): Promise<'ok' | 'error' | 'reintentar' | 'sin_conexion' | 'sesion'> {
  await guardarOperacion({ ...op, estado: 'sincronizando', intentos: op.intentos + 1 })
  try {
    const r = await api.post<Lectura & { ya_recibida: boolean; deudas?: DeudasLectura }>('cobrador/lecturas/', formulario(op), { timeout: 120_000 })
    await guardarOperacion({
      ...op, intentos: op.intentos + 1, estado: r.data.estado === 'requiere_revision' ? 'revision' : 'sincronizada',
      comprobante: r.data.comprobante, consumo: r.data.consumo, estado_servidor: r.data.estado_nombre,
      motivo_revision: r.data.motivo_revision_nombre, deudas: r.data.deudas, error: undefined,
      foto: null, adicionales: [], // confirmadas por el servidor: ya no hace falta guardarlas en el teléfono
      sincronizada_en: new Date().toISOString(),
    })
    return 'ok'
  } catch (e) {
    if (axios.isAxiosError(e) && e.response && e.response.status >= 400 && e.response.status < 500 && e.response.status !== 401
        && e.response.status !== 408 && e.response.status !== 429) {
      const datos = e.response.data as { detalle?: string } | undefined
      await guardarOperacion({ ...op, intentos: op.intentos + 1, estado: 'error', error: datos?.detalle ?? `Rechazada (${e.response.status}).` })
      return 'error'
    }
    // Sin conexión, sesión vencida o error del servidor: vuelve a quedar pendiente con todo intacto.
    await guardarOperacion({ ...op, intentos: op.intentos + 1, estado: 'pendiente' })
    if (axios.isAxiosError(e) && e.response?.status === 401) return 'sesion'
    if (axios.isAxiosError(e) && e.response) return 'reintentar' // el servidor respondió con error: sigue con las demás
    return 'sin_conexion'
  }
}

export function sincronizar(api: AxiosInstance, usuario: string): Promise<ResultadoSincronizacion> {
  if (enCurso) return enCurso
  enCurso = (async () => {
    const resultado: ResultadoSincronizacion = { enviadas: 0, errores: 0, sinConexion: false, sesionVencida: false }
    try {
      const ops = (await operacionesDe(usuario)).filter((o) => o.estado === 'pendiente' || o.estado === 'sincronizando')
      for (const op of ops) {
        const r = await enviarOperacion(api, op)
        if (r === 'ok') resultado.enviadas++
        else if (r === 'error' || r === 'reintentar') resultado.errores++
        else {
          resultado.sinConexion = r === 'sin_conexion'
          resultado.sesionVencida = r === 'sesion'
          break
        }
      }
    } finally {
      enCurso = null
    }
    return resultado
  })()
  return enCurso
}
