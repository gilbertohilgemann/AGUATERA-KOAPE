import type { ReactNode } from 'react'

/** Etiqueta + control, para formularios compactos. */
export function Campo({ etiqueta, children, ancho = false }: { etiqueta: string; children: ReactNode; ancho?: boolean }) {
  return (
    <label className={`block ${ancho ? 'sm:col-span-2' : ''}`}>
      <span className="etiqueta">{etiqueta}</span>
      {children}
    </label>
  )
}
