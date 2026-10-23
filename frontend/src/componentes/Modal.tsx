import type { ReactNode } from 'react'

export function Modal({ titulo, alCerrar, children, amplio = false, completo = false }: { titulo: string; alCerrar: () => void; children: ReactNode; amplio?: boolean; completo?: boolean }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-koape-tinta/50 p-4" onMouseDown={alCerrar}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        className={`tarjeta max-h-[90vh] w-full ${completo ? 'max-w-6xl' : amplio ? 'max-w-4xl' : 'max-w-2xl'} overflow-y-auto p-6`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 className="text-lg font-bold">{titulo}</h2>
          <button className="text-2xl leading-none text-koape-gris hover:text-koape-rojo" onClick={alCerrar} aria-label="Cerrar">
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
