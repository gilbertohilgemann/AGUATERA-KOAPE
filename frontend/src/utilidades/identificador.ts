/**
 * Identificador único para cada pedido (va en X-Id-Solicitud y queda en la auditoría).
 *
 * Lección aprendida (convenciones): `crypto.randomUUID()` NO existe en HTTP plano sobre un host que no
 * sea localhost (restricción de «contexto seguro»). Sin este respaldo, el sistema se cae entero en la red
 * local o en el servidor hasta que haya HTTPS.
 */
export function nuevoIdentificador(): string {
  const c = typeof globalThis !== 'undefined' ? globalThis.crypto : undefined
  if (c && typeof c.randomUUID === 'function') {
    try {
      return c.randomUUID()
    } catch {
      /* contexto no seguro: se usa el respaldo */
    }
  }
  const bytes = new Uint8Array(16)
  if (c && typeof c.getRandomValues === 'function') c.getRandomValues(bytes)
  else for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256)
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
