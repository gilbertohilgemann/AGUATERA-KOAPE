/**
 * Achica una foto antes de subirla (lado mayor 1600 px, JPEG 80 %): menos datos móviles y menos
 * espacio en el servidor. Si el navegador no puede procesarla, se sube la original.
 */
export async function comprimirImagen(archivo: File, ladoMaximo = 1600, calidad = 0.8): Promise<Blob> {
  if (!archivo.type.startsWith('image/') || typeof createImageBitmap !== 'function') return archivo
  try {
    const imagen = await createImageBitmap(archivo)
    const escala = Math.min(1, ladoMaximo / Math.max(imagen.width, imagen.height))
    const lienzo = document.createElement('canvas')
    lienzo.width = Math.round(imagen.width * escala)
    lienzo.height = Math.round(imagen.height * escala)
    const contexto = lienzo.getContext('2d')
    if (!contexto) return archivo
    contexto.drawImage(imagen, 0, 0, lienzo.width, lienzo.height)
    imagen.close()
    const resultado = await new Promise<Blob | null>((ok) => lienzo.toBlob(ok, 'image/jpeg', calidad))
    return resultado && resultado.size < archivo.size ? resultado : archivo
  } catch {
    return archivo
  }
}
