import type { ReactNode } from 'react'

const estilos = {
  error: 'border-koape-rojo/40 bg-koape-rojo/5 text-koape-rojo',
  exito: 'border-emerald-300 bg-emerald-50 text-emerald-800',
  info: 'border-koape-amarillo/60 bg-koape-amarillo/10 text-koape-tinta',
}

export function Aviso({ tipo = 'info', children }: { tipo?: keyof typeof estilos; children: ReactNode }) {
  if (!children) return null
  return (
    <div role={tipo === 'error' ? 'alert' : 'status'} className={`rounded-lg border px-3 py-2 text-sm ${estilos[tipo]}`}>
      {children}
    </div>
  )
}
