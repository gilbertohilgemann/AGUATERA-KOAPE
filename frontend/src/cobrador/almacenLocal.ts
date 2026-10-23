import type { PaqueteRecorrido } from '../api/tipos'

/**
 * Almacenamiento del teléfono (IndexedDB) para trabajar sin conexión (sección 10):
 * - `paquetes`: los recorridos descargados (conexiones, titulares, lecturas anteriores).
 * - `operaciones`: las lecturas tomadas, con sus fotos, hasta que el servidor confirme que las recibió.
 *
 * Todo queda asociado al usuario que lo tomó: si otra persona ingresa en el mismo teléfono no ve ni envía
 * lo ajeno. Las fotos se borran del teléfono recién cuando el servidor confirma la lectura con sus fotos.
 */

export type EstadoOperacion = 'pendiente' | 'sincronizando' | 'sincronizada' | 'error' | 'revision'

export interface Operacion {
  id_operacion: string
  usuario: string // CODIGO/usuario: dueño de la operación
  recorrido: string
  conexion: string
  medidor: string
  lectura_actual: string
  capturada_en: string
  latitud: number
  longitud: number
  precision_metros: number | null
  comentario: string
  foto_origen: 'camara' | 'galeria'
  foto: Blob | null
  adicionales: Blob[]
  estado: EstadoOperacion
  intentos: number
  error?: string
  comprobante?: string
  consumo?: string | null
  estado_servidor?: string
  motivo_revision?: string
  deudas?: import('../api/tipos').DeudasLectura
  creada_en: string
  sincronizada_en?: string
}

const BASE = 'koape-aguateras'
const VERSION = 1
let conexion: Promise<IDBDatabase> | null = null

function abrir(): Promise<IDBDatabase> {
  if (conexion) return conexion
  conexion = new Promise((ok, falla) => {
    const pedido = indexedDB.open(BASE, VERSION)
    pedido.onupgradeneeded = () => {
      const db = pedido.result
      if (!db.objectStoreNames.contains('paquetes')) db.createObjectStore('paquetes', { keyPath: 'clave' })
      if (!db.objectStoreNames.contains('operaciones')) {
        const ops = db.createObjectStore('operaciones', { keyPath: 'id_operacion' })
        ops.createIndex('usuario', 'usuario')
      }
    }
    pedido.onsuccess = () => ok(pedido.result)
    pedido.onerror = () => {
      conexion = null
      falla(pedido.error ?? new Error('No se pudo abrir el almacenamiento del teléfono.'))
    }
  })
  return conexion
}

function promesa<T>(pedido: IDBRequest<T>): Promise<T> {
  return new Promise((ok, falla) => {
    pedido.onsuccess = () => ok(pedido.result)
    pedido.onerror = () => falla(pedido.error)
  })
}

async function almacen(nombre: 'paquetes' | 'operaciones', modo: IDBTransactionMode) {
  const db = await abrir()
  return db.transaction(nombre, modo).objectStore(nombre)
}

// --- Paquetes -----------------------------------------------------------------------------------

interface PaqueteGuardado {
  clave: string
  usuario: string
  code: string
  descargado_en: string
  paquete: PaqueteRecorrido
}

const clavePaquete = (usuario: string, code: string) => `${usuario}|${code}`

export async function guardarPaquete(usuario: string, paquete: PaqueteRecorrido): Promise<void> {
  const registro: PaqueteGuardado = {
    clave: clavePaquete(usuario, paquete.recorrido.Code), usuario, code: paquete.recorrido.Code,
    descargado_en: new Date().toISOString(), paquete,
  }
  await promesa((await almacen('paquetes', 'readwrite')).put(registro))
}

export async function leerPaquete(usuario: string, code: string): Promise<{ paquete: PaqueteRecorrido; descargado_en: string } | null> {
  const r = await promesa<PaqueteGuardado | undefined>((await almacen('paquetes', 'readonly')).get(clavePaquete(usuario, code)))
  return r ? { paquete: r.paquete, descargado_en: r.descargado_en } : null
}

export async function paquetesDe(usuario: string): Promise<PaqueteGuardado[]> {
  const todos = await promesa<PaqueteGuardado[]>((await almacen('paquetes', 'readonly')).getAll())
  return todos.filter((p) => p.usuario === usuario)
}

export async function borrarPaquete(usuario: string, code: string): Promise<void> {
  await promesa((await almacen('paquetes', 'readwrite')).delete(clavePaquete(usuario, code)))
}

/** Datos personales: no quedan indefinidamente en el teléfono (sección 10.2). */
export async function limpiarPaquetesViejos(dias = 45): Promise<void> {
  const limite = Date.now() - dias * 86_400_000
  const tienda = await almacen('paquetes', 'readwrite')
  const todos = await promesa<PaqueteGuardado[]>(tienda.getAll())
  for (const p of todos) if (new Date(p.descargado_en).getTime() < limite) tienda.delete(p.clave)
}

// --- Operaciones (lecturas tomadas) ---------------------------------------------------------------

export async function guardarOperacion(op: Operacion): Promise<void> {
  await promesa((await almacen('operaciones', 'readwrite')).put(op))
}

export async function operacionesDe(usuario: string): Promise<Operacion[]> {
  const tienda = await almacen('operaciones', 'readonly')
  const lista = await promesa<Operacion[]>(tienda.index('usuario').getAll(usuario))
  return lista.sort((a, b) => a.creada_en.localeCompare(b.creada_en))
}

export async function leerOperacion(id: string): Promise<Operacion | undefined> {
  return promesa<Operacion | undefined>((await almacen('operaciones', 'readonly')).get(id))
}

export async function borrarOperacion(id: string): Promise<void> {
  await promesa((await almacen('operaciones', 'readwrite')).delete(id))
}

/** Las ya confirmadas por el servidor (sin fotos) se borran del teléfono pasados unos días. */
export async function limpiarSincronizadas(usuario: string, dias = 7): Promise<void> {
  const limite = Date.now() - dias * 86_400_000
  for (const op of await operacionesDe(usuario)) {
    if ((op.estado === 'sincronizada' || op.estado === 'revision') && op.sincronizada_en
        && new Date(op.sincronizada_en).getTime() < limite) {
      await borrarOperacion(op.id_operacion)
    }
  }
}

export const pendientes = (ops: Operacion[]) => ops.filter((o) => o.estado === 'pendiente' || o.estado === 'sincronizando' || o.estado === 'error')
