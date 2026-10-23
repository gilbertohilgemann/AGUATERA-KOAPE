const formato = new Intl.DateTimeFormat('es-PY', { dateStyle: 'short', timeStyle: 'short' })

export function fechaHora(valor: string | null | undefined): string {
  if (!valor) return '—'
  const fecha = new Date(valor)
  return Number.isNaN(fecha.getTime()) ? '—' : formato.format(fecha)
}
