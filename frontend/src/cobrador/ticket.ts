import type { AxiosInstance } from 'axios'
import { mensajeDeError } from '../api/cliente'

const CLAVE_ANCHO = 'koape.ticket.ancho'

/** Ancho del papel de la impresora térmica de este teléfono (58 u 80 mm); se recuerda en el teléfono. */
export function anchoTicket(): '58' | '80' {
  try { return localStorage.getItem(CLAVE_ANCHO) === '80' ? '80' : '58' } catch { return '58' }
}

export function guardarAnchoTicket(ancho: '58' | '80') {
  try { localStorage.setItem(CLAVE_ANCHO, ancho) } catch { /* sin almacenamiento: queda 58 mm */ }
}

/**
 * Abre el ticket (PDF angosto) para imprimirlo o compartirlo con la aplicación de la impresora Bluetooth.
 * Devuelve el mensaje de error, o '' si se abrió.
 */
export async function abrirTicket(api: AxiosInstance, comprobante: string): Promise<string> {
  const ventana = window.open('', '_blank')
  try {
    const r = await api.get<Blob>(`cobrador/lecturas/${comprobante}/ticket/`, { params: { ancho: anchoTicket() }, responseType: 'blob' })
    const url = URL.createObjectURL(r.data)
    if (ventana) ventana.location.href = url
    else window.location.href = url
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
    return ''
  } catch (e) {
    ventana?.close()
    return mensajeDeError(e)
  }
}
