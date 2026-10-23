/** Isotipo + logotipo "KOAPE SISTEMAS EAS" (manual de marca 2026). */
export function Logo({ claro = false, compacto = false, grande = false }: { claro?: boolean; compacto?: boolean; grande?: boolean }) {
  const imagen = compacto ? 'h-9 w-auto' : grande ? 'h-32 w-auto xl:h-40' : 'h-14 w-auto'
  const texto = compacto ? 'text-sm' : grande ? 'text-4xl xl:text-5xl' : 'text-xl'
  return (
    <div className={`flex items-center ${grande ? 'gap-6' : 'gap-3'}`}>
      <img src="/isotipo-koape.png" alt="" className={imagen} />
      <div
        className={`font-titulo font-extrabold leading-[1.05] tracking-wide ${claro ? 'text-white' : 'text-koape-tinta'} ${texto}`}
      >
        KOAPE
        <br />
        SISTEMAS
        <br />
        EAS
      </div>
    </div>
  )
}
