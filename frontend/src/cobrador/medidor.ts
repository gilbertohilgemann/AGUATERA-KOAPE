import type { ConexionPaquete } from '../api/tipos'

/** Cómo se muestra el medidor al cobrador: primero el número grabado en el aparato, después el código interno. */
export function nombreMedidor(c: Pick<ConexionPaquete, 'medidor' | 'medidor_numero'>): string {
  if (!c.medidor) return '—'
  return c.medidor_numero ? `N.º ${c.medidor_numero} (${c.medidor})` : c.medidor
}

/** Lo que se precarga al ir a leer un medidor desde la lista o el mapa: lo que el cobrador verá grabado. */
export function identificacionMedidor(c: Pick<ConexionPaquete, 'medidor' | 'medidor_numero'>): string {
  return c.medidor_numero || c.medidor || ''
}

/**
 * Búsqueda dentro del recorrido: por número de orden o por número / código del medidor.
 * Unos pocos dígitos («3», «12») son el orden de visita (o un número de medidor exacto); con letras o desde 4
 * caracteres se busca dentro del número o código del medidor («a231», «48213»).
 */
export function coincide(c: Pick<ConexionPaquete, 'orden' | 'medidor' | 'medidor_numero'>, texto: string): boolean {
  const t = texto.trim().toUpperCase().replace(/^N\.?º\s*/, '')
  if (!t) return true
  const numero = (c.medidor_numero ?? '').toUpperCase()
  const codigo = (c.medidor ?? '').toUpperCase()
  if (/^\d+$/.test(t) && c.orden === Number(t)) return true
  if (t.length < 4 && !/[A-Z]/.test(t)) return numero === t || codigo === t
  return numero.includes(t) || codigo.includes(t)
}
