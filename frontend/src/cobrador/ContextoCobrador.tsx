import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useSesion } from '../sesion/ContextoSesion'
import { limpiarPaquetesViejos, limpiarSincronizadas, operacionesDe, pendientes, type Operacion } from './almacenLocal'
import { sincronizar, type ResultadoSincronizacion } from './sincronizacion'

interface ValorCobrador {
  /** Dueño de los datos del teléfono: CODIGO/usuario. */
  usuario: string
  enLinea: boolean
  operaciones: Operacion[]
  cantidadPendientes: number
  sincronizando: boolean
  ultimo: ResultadoSincronizacion | null
  recargar: () => Promise<void>
  sincronizarAhora: () => Promise<void>
}

const Contexto = createContext<ValorCobrador | null>(null)

export function useCobrador(): ValorCobrador {
  const valor = useContext(Contexto)
  if (!valor) throw new Error('useCobrador debe usarse dentro de <ProveedorCobrador>')
  return valor
}

const CADA_MS = 60_000

export function ProveedorCobrador({ children }: { children: ReactNode }) {
  const { api, datos } = useSesion()
  const usuario = `${datos.institucion.codigo}/${datos.usuario.usuario}`
  const [enLinea, setEnLinea] = useState(() => navigator.onLine)
  const [operaciones, setOperaciones] = useState<Operacion[]>([])
  const [sincronizando, setSincronizando] = useState(false)
  const [ultimo, setUltimo] = useState<ResultadoSincronizacion | null>(null)
  const montado = useRef(true)

  const recargar = useCallback(async () => {
    try {
      const ops = await operacionesDe(usuario)
      if (montado.current) setOperaciones(ops)
    } catch {
      /* sin IndexedDB (modo privado): la aplicación avisa al guardar */
    }
  }, [usuario])

  const sincronizarAhora = useCallback(async () => {
    setSincronizando(true)
    try {
      const r = await sincronizar(api, usuario)
      if (montado.current) setUltimo(r)
    } finally {
      if (montado.current) setSincronizando(false)
      await recargar()
    }
  }, [api, usuario, recargar])

  useEffect(() => {
    montado.current = true
    // Pedir al navegador que no borre los datos del teléfono por falta de espacio (lecturas sin enviar).
    void navigator.storage?.persist?.().catch(() => undefined)
    void limpiarPaquetesViejos().catch(() => undefined)
    void limpiarSincronizadas(usuario).catch(() => undefined)
    void recargar()
    const alConectar = () => { setEnLinea(true); void sincronizarAhora() }
    const alDesconectar = () => setEnLinea(false)
    window.addEventListener('online', alConectar)
    window.addEventListener('offline', alDesconectar)
    const intervalo = window.setInterval(() => { if (navigator.onLine) void sincronizarAhora() }, CADA_MS)
    if (navigator.onLine) void sincronizarAhora()
    return () => {
      montado.current = false
      window.removeEventListener('online', alConectar)
      window.removeEventListener('offline', alDesconectar)
      window.clearInterval(intervalo)
    }
  }, [usuario, recargar, sincronizarAhora])

  const valor = useMemo<ValorCobrador>(() => ({
    usuario, enLinea, operaciones, cantidadPendientes: pendientes(operaciones).length, sincronizando, ultimo,
    recargar, sincronizarAhora,
  }), [usuario, enLinea, operaciones, sincronizando, ultimo, recargar, sincronizarAhora])

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>
}
