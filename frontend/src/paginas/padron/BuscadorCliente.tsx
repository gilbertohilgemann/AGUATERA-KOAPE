import { useEffect, useState } from 'react'
import type { Cliente, Pagina } from '../../api/tipos'
import { useSesion } from '../../sesion/ContextoSesion'

/** Elige un cliente escribiendo parte del nombre, código o documento. */
export function BuscadorCliente({ valor, alElegir }: { valor: Pick<Cliente, 'Code' | 'nombre'> | null; alElegir: (c: Cliente) => void }) {
  const { api } = useSesion()
  const [texto, setTexto] = useState('')
  const [opciones, setOpciones] = useState<Cliente[]>([])
  const [abierto, setAbierto] = useState(false)

  useEffect(() => {
    if (!abierto) return
    const temporizador = setTimeout(() => {
      api.get<Pagina<Cliente>>('clientes/', { params: { buscar: texto || undefined, tamanio: 15 } })
        .then((r) => setOpciones(r.data.results)).catch(() => setOpciones([]))
    }, 250)
    return () => clearTimeout(temporizador)
  }, [api, texto, abierto])

  return (
    <div className="relative">
      <input className="campo" value={abierto ? texto : valor ? `${valor.Code} · ${valor.nombre}` : ''} placeholder="Buscar cliente…"
        onFocus={() => { setAbierto(true); setTexto('') }} onBlur={() => setTimeout(() => setAbierto(false), 200)}
        onChange={(e) => setTexto(e.target.value)} />
      {abierto && (
        <ul className="absolute z-[1000] mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-koape-gris-claro bg-white shadow-lg">
          {opciones.map((c) => (
            <li key={c.Code}>
              <button type="button" className="block w-full px-3 py-2 text-left text-sm hover:bg-koape-fondo"
                onMouseDown={() => { alElegir(c); setAbierto(false) }}>
                <b>{c.Code}</b> · {c.nombre}{c.documento ? ` · ${c.documento}` : ''}
              </button>
            </li>
          ))}
          {opciones.length === 0 && <li className="px-3 py-2 text-sm text-koape-gris">Sin resultados.</li>}
        </ul>
      )}
    </div>
  )
}
