/**
 * Token de sesión.
 * - Panel de oficina: sessionStorage (se borra al cerrar la pestaña).
 * - Aplicación del cobrador: además se recuerda en este teléfono (localStorage) para poder seguir trabajando
 *   sin conexión aunque se cierre la aplicación. Vence igual a las 12 h y se borra al «Salir».
 * Todo acceso va con try/catch: con almacenamiento bloqueado el sistema sigue funcionando en memoria.
 */
const CLAVE = 'koape.aguateras.sesion'
const CLAVE_YO = 'koape.aguateras.yo'
let enMemoria: string | null = null

export function leerToken(): string | null {
  try {
    return window.sessionStorage.getItem(CLAVE) ?? window.localStorage.getItem(CLAVE) ?? enMemoria
  } catch {
    return enMemoria
  }
}

/** Ingreso nuevo: descarta lo recordado de una sesión anterior (puede ser de otra persona en el mismo teléfono). */
export function guardarToken(token: string): void {
  enMemoria = token
  try {
    window.localStorage.removeItem(CLAVE)
    window.localStorage.removeItem(CLAVE_YO)
    window.sessionStorage.setItem(CLAVE, token)
  } catch {
    /* sin almacenamiento: queda en memoria */
  }
}

/** Modo cobrador: recuerda la sesión en este teléfono hasta que venza o se salga. */
export function recordarEnEsteEquipo(): void {
  const token = leerToken()
  if (!token) return
  try {
    window.localStorage.setItem(CLAVE, token)
  } catch {
    /* sin almacenamiento persistente */
  }
}

export function borrarToken(): void {
  enMemoria = null
  try {
    window.sessionStorage.removeItem(CLAVE)
    window.localStorage.removeItem(CLAVE)
    window.localStorage.removeItem(CLAVE_YO)
  } catch {
    /* nada que borrar */
  }
}

const huella = (token: string | null) => (token ? token.slice(-16) : '')

/** Copia de los datos de la sesión para abrir la aplicación del cobrador sin conexión (atada a ESTE token). */
export function guardarDatosSesion(datos: unknown): void {
  try {
    window.localStorage.setItem(CLAVE_YO, JSON.stringify({ token: huella(leerToken()), datos }))
  } catch {
    /* sin almacenamiento */
  }
}

/** Solo devuelve la copia si corresponde al token actual (nunca la de otra persona). */
export function leerDatosSesion<T>(): T | null {
  try {
    const texto = window.localStorage.getItem(CLAVE_YO)
    if (!texto) return null
    const copia = JSON.parse(texto) as { token?: string; datos?: T }
    return copia.token && copia.token === huella(leerToken()) && copia.datos ? copia.datos : null
  } catch {
    return null
  }
}
