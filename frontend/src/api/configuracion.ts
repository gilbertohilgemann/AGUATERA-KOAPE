/**
 * Dirección de la API, armada sola a partir del host desde el que se ve la página (así se puede probar
 * desde el celular u otra PC de la red sin editar IPs). Solo se usa una variable explícita cuando está
 * seteada (convenciones, «desarrollo sin fricción»).
 */
export function urlApi(): string {
  const env = import.meta.env
  if (env.VITE_API_URL) return env.VITE_API_URL.replace(/\/?$/, '/')
  if (env.VITE_API_MISMO_ORIGEN) return '/api/v1/'
  const puerto = env.VITE_API_PUERTO || '9006'
  return `${window.location.protocol}//${window.location.hostname}:${puerto}/api/v1/`
}

/** Dirección absoluta de un archivo que devuelve la API (ej. el logo). */
export function urlArchivo(ruta: string | null | undefined): string | undefined {
  if (!ruta) return undefined
  if (/^https?:\/\//.test(ruta)) return ruta
  return new URL(ruta, urlApi()).toString()
}
