export function Paginador({ pagina, total, tamanio = 50, alCambiar }: { pagina: number; total: number; tamanio?: number; alCambiar: (p: number) => void }) {
  const paginas = Math.max(1, Math.ceil(total / tamanio))
  return (
    <div className="mt-3 flex items-center justify-between text-sm text-koape-gris">
      <span>{total} registro(s)</span>
      <div className="flex items-center gap-2">
        <button className="boton-secundario" disabled={pagina <= 1} onClick={() => alCambiar(pagina - 1)}>Anterior</button>
        <span>{pagina} / {paginas}</span>
        <button className="boton-secundario" disabled={pagina >= paginas} onClick={() => alCambiar(pagina + 1)}>Siguiente</button>
      </div>
    </div>
  )
}
