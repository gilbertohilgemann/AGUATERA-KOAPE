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

/** UTF-8 a base64 (btoa solo acepta Latin-1). */
function base64Utf8(texto: string): string {
  return btoa(unescape(encodeURIComponent(texto)))
}

/**
 * Intenta imprimir directo en la ticketera con la app RawBT (en el Sunmi V2 Pro maneja la impresora integrada).
 * Si RawBT no está instalada el navegador no cambia de aplicación; devuelve true si la app se abrió.
 */
function imprimirConRawBT(texto: string): Promise<boolean> {
  return new Promise((resolver) => {
    let abierta = false
    const marcar = () => { if (document.hidden) abierta = true }
    const alSalir = () => { abierta = true }
    document.addEventListener('visibilitychange', marcar)
    window.addEventListener('pagehide', alSalir)
    window.addEventListener('blur', alSalir)
    window.location.href = `intent:base64,${base64Utf8(texto)}#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;`
    setTimeout(() => {
      document.removeEventListener('visibilitychange', marcar)
      window.removeEventListener('pagehide', alSalir)
      window.removeEventListener('blur', alSalir)
      resolver(abierta)
    }, 1500)
  })
}

/**
 * Imprime el ticket directo en la ticketera (RawBT); si no la encuentra, lo abre como PDF (angosto) para
 * imprimirlo o compartirlo. Devuelve el mensaje de error, o '' si salió bien.
 */
export async function abrirTicket(api: AxiosInstance, comprobante: string): Promise<string> {
  const ruta = `cobrador/lecturas/${comprobante}/ticket/`
  const ancho = anchoTicket()
  try {
    const [texto, pdf] = await Promise.all([
      api.get<string>(ruta, { params: { ancho, formato: 'texto' }, responseType: 'text', transformResponse: (d) => d }),
      api.get<Blob>(ruta, { params: { ancho }, responseType: 'blob' }),
    ])
    if (await imprimirConRawBT(texto.data)) return ''
    const url = URL.createObjectURL(pdf.data)
    window.location.href = url
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
    return ''
  } catch (e) {
    return mensajeDeError(e)
  }
}
