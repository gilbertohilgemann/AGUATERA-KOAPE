import { useEffect, useState } from 'react'
import { useSesion } from '../sesion/ContextoSesion'

/**
 * Muestra una foto privada: se pide con el token de la sesión (una etiqueta <img> común no puede
 * mandarlo) y se muestra desde memoria. Nunca hay una URL pública de la foto.
 */
export function FotoPrivada({ ruta, version, alt, className = '' }: { ruta: string; version?: string; alt: string; className?: string }) {
  const { api } = useSesion()
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let vigente = true
    let creada: string | null = null
    setError(false)
    api.get<Blob>(ruta, { responseType: 'blob' })
      .then((r) => {
        if (!vigente) return
        creada = URL.createObjectURL(r.data)
        setUrl(creada)
      })
      .catch(() => vigente && setError(true))
    return () => {
      vigente = false
      if (creada) URL.revokeObjectURL(creada)
    }
  }, [api, ruta, version])

  if (error) return <div className="grid h-40 place-items-center rounded-lg bg-koape-fondo text-xs text-koape-gris">No se pudo cargar la foto.</div>
  if (!url) return <div className="grid h-40 place-items-center rounded-lg bg-koape-fondo text-xs text-koape-gris">Cargando foto…</div>
  return <img src={url} alt={alt} className={className} />
}
