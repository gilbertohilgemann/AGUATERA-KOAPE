import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import type { ConexionPaquete, PaqueteRecorrido } from '../api/tipos'
import { Aviso } from '../componentes/Aviso'
import { FotoPrivada } from '../componentes/FotoPrivada'
import { useSesion } from '../sesion/ContextoSesion'
import { nuevoIdentificador } from '../utilidades/identificador'
import { comprimirImagen } from '../utilidades/imagenes'
import { guardarOperacion, leerOperacion, leerPaquete, type Operacion } from './almacenLocal'
import { useCobrador } from './ContextoCobrador'
import { nombreMedidor } from './medidor'
import { abrirTicket } from './ticket'
import { enviarOperacion } from './sincronizacion'

type Paso = 'medidor' | 'foto' | 'lectura' | 'listo'
type Posicion = { latitud: number; longitud: number; precision: number }

const fmt = (v: string | number | null | undefined) =>
  v === null || v === undefined || v === '' ? '—' : Number(v).toLocaleString('es-PY', { maximumFractionDigits: 3 })

/** GPS obligatorio (decisión 20/10/2026): se sigue la posición mientras se toma la lectura. */
function useGps(activo: boolean) {
  const [posicion, setPosicion] = useState<Posicion | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!activo) return
    if (!('geolocation' in navigator)) {
      setError('Este teléfono o navegador no ofrece ubicación.')
      return
    }
    const id = navigator.geolocation.watchPosition(
      (p) => { setPosicion({ latitud: p.coords.latitude, longitud: p.coords.longitude, precision: p.coords.accuracy }); setError('') },
      (e) => setError(e.code === e.PERMISSION_DENIED
        ? 'Permita el acceso a la ubicación para esta aplicación (configuración del navegador o del teléfono). Sin GPS no se puede guardar la lectura.'
        : window.isSecureContext ? 'Buscando señal de GPS… Si tarda, salga a un lugar abierto y verifique que la ubicación esté activada.'
          : 'El GPS solo funciona con la dirección segura (https).'),
      { enableHighAccuracy: true, maximumAge: 15_000, timeout: 30_000 },
    )
    return () => navigator.geolocation.clearWatch(id)
  }, [activo])
  return { posicion, error }
}

function normalizarNumero(texto: string): string | null {
  const limpio = texto.trim().replace(/\s/g, '').replace(',', '.')
  return /^\d+(\.\d{1,3})?$/.test(limpio) ? limpio : null
}

export function TomarLectura() {
  const { code = '' } = useParams()
  const { api, datos, sinConexion } = useSesion()
  const { usuario, enLinea, operaciones, recargar } = useCobrador()
  const [paquete, setPaquete] = useState<PaqueteRecorrido | null>(null)
  const [paso, setPaso] = useState<Paso>('medidor')
  const [parametros] = useSearchParams()
  const [medidor, setMedidor] = useState(() => (parametros.get('medidor') ?? '').toUpperCase())
  const [conexion, setConexion] = useState<ConexionPaquete | null>(null)
  const [foto, setFoto] = useState<{ blob: Blob; url: string; origen: 'camara' | 'galeria' } | null>(null)
  const [adicionales, setAdicionales] = useState<Blob[]>([])
  const [valor, setValor] = useState('')
  const [comentario, setComentario] = useState('')
  const [error, setError] = useState('')
  const [guardando, setGuardando] = useState(false)
  const [resultado, setResultado] = useState<Operacion | null>(null)
  const [desconocido, setDesconocido] = useState('')
  const capturada = useRef<string>('')
  const { posicion, error: errorGps } = useGps(paso === 'foto' || paso === 'lectura')
  const enRed = enLinea && !sinConexion

  useEffect(() => {
    leerPaquete(usuario, code).then((p) => setPaquete(p?.paquete ?? null)).catch(() => setPaquete(null))
  }, [usuario, code])

  useEffect(() => () => { if (foto) URL.revokeObjectURL(foto.url) }, [foto])

  if (!paquete) return <p className="text-koape-gris">Cargando el recorrido del teléfono…</p>
  const permiteGaleria = paquete.institucion.permite_galeria || datos.institucion.lecturas_permite_galeria
  const yaLocal = conexion ? operaciones.find((o) => o.conexion === conexion.conexion && o.recorrido === code && o.estado !== 'error') : undefined

  // Paso 1: identificar el medidor: el número grabado en el aparato (o su código interno, si no tiene número).
  function identificar(e: FormEvent) {
    e.preventDefault()
    setError('')
    const buscado = medidor.trim().toUpperCase()
    const encontrada = paquete?.conexiones.find((c) => !!c.medidor_numero && c.medidor_numero === buscado)
      ?? paquete?.conexiones.find((c) => c.medidor === buscado)
    if (!encontrada) {
      if (!desconocido) {
        setDesconocido(buscado)
        setError(`El medidor ${buscado} no está en el recorrido descargado. Verifique el número. Si es correcto (por ejemplo, lo cambiaron hace poco), toque «Continuar» de nuevo: la lectura se guarda y la revisa la oficina.`)
        return
      }
      setConexion({
        orden: 0, conexion: '', titular: 'No figura en el recorrido descargado', direccion: '', barrio: '', lat: null, lon: null,
        tiene_foto_vivienda: false, medidor: buscado, medidor_numero: '', unidad: null, lectura_maxima: null, lectura_anterior: null,
        fecha_lectura_anterior: null, leida: null,
      })
      setPaso('foto')
      return
    }
    setDesconocido('')
    setConexion(encontrada)
    setPaso('foto')
  }

  // Paso 2: foto obligatoria antes de ver los datos.
  async function elegirFoto(archivo: File | undefined, origen: 'camara' | 'galeria') {
    if (!archivo) return
    setError('')
    if (!archivo.type.startsWith('image/')) {
      setError('El archivo no es una foto.')
      return
    }
    const blob = await comprimirImagen(archivo)
    capturada.current = new Date().toISOString()
    setFoto({ blob, url: URL.createObjectURL(blob), origen })
    setPaso('lectura')
  }

  async function agregarAdicional(archivo: File | undefined) {
    if (!archivo || adicionales.length >= 3) return
    setAdicionales([...adicionales, await comprimirImagen(archivo)])
  }

  // Pasos 4 y 5: validar y confirmar. Se guarda primero en el teléfono; después se envía.
  async function confirmar(e: FormEvent) {
    e.preventDefault()
    if (!conexion || !foto || !posicion) return
    setError('')
    const numero = normalizarNumero(valor)
    if (numero === null) {
      setError('Escriba la lectura con números (hasta 3 decimales).')
      return
    }
    if (conexion.lectura_maxima && Number(numero) > Number(conexion.lectura_maxima)) {
      setError(`La lectura supera la capacidad del medidor (${fmt(conexion.lectura_maxima)}). Revise el número.`)
      return
    }
    const menor = conexion.lectura_anterior !== null && Number(numero) < Number(conexion.lectura_anterior)
    if (menor && !comentario.trim()) {
      setError('La lectura es menor que la anterior. Si es correcta, explique en el comentario qué pasó (quedará en revisión).')
      return
    }
    setGuardando(true)
    const op: Operacion = {
      id_operacion: nuevoIdentificador(), usuario, recorrido: code, conexion: conexion.conexion, medidor: conexion.medidor ?? medidor,
      lectura_actual: numero, capturada_en: capturada.current || new Date().toISOString(), latitud: posicion.latitud,
      longitud: posicion.longitud, precision_metros: posicion.precision, comentario: comentario.trim(), foto_origen: foto.origen,
      foto: foto.blob, adicionales, estado: 'pendiente', intentos: 0, creada_en: new Date().toISOString(),
    }
    try {
      await guardarOperacion(op)
    } catch {
      setGuardando(false)
      setError('No se pudo guardar en el teléfono (¿navegación privada o sin espacio?). La lectura no se registró.')
      return
    }
    try {
      if (enRed) await enviarOperacion(api, op)
      setResultado((await leerOperacion(op.id_operacion)) ?? op)
      await recargar()
    } catch {
      setResultado(op) // quedó guardada en el teléfono; se envía en la próxima sincronización
    } finally {
      setGuardando(false)
      setPaso('listo')
    }
  }

  function otra() {
    setPaso('medidor')
    setMedidor('')
    setConexion(null)
    setFoto(null)
    setAdicionales([])
    setValor('')
    setComentario('')
    setResultado(null)
    setDesconocido('')
    setError('')
  }

  const estimado = conexion?.lectura_anterior !== null && conexion?.lectura_anterior !== undefined && normalizarNumero(valor) !== null
    ? Number(normalizarNumero(valor)) - Number(conexion.lectura_anterior) : null

  return (
    <div className="space-y-4">
      <p className="text-sm"><Link className="text-koape-rojo" to={`/cobrador/r/${code}`}>← {paquete.recorrido.nombre}</Link></p>
      <ol className="flex gap-1 text-[11px] font-semibold text-koape-gris">
        {['Medidor', 'Foto', 'Lectura', 'Listo'].map((t, i) => (
          <li key={t} className={`flex-1 rounded-full py-1 text-center ${['medidor', 'foto', 'lectura', 'listo'].indexOf(paso) >= i ? 'bg-koape-rojo text-white' : 'bg-white'}`}>{i + 1}. {t}</li>
        ))}
      </ol>
      <Aviso tipo="error">{error}</Aviso>

      {paso === 'medidor' && (
        <form onSubmit={identificar} className="space-y-3 rounded-xl bg-white p-4 shadow-sm">
          <label className="block">
            <span className="etiqueta">Número del medidor</span>
            <input className="campo py-3 text-center text-2xl font-bold tracking-widest uppercase" autoFocus autoCapitalize="characters"
              autoComplete="off" value={medidor} onChange={(e) => { setMedidor(e.target.value); setDesconocido('') }} placeholder="Ej. A23057X" />
          </label>
          <p className="text-xs text-koape-gris">Escriba el número que está grabado en el medidor (o su código, si no tiene número cargado).</p>
          <button className="boton-primario w-full py-3 text-lg" disabled={!medidor.trim()}>Continuar</button>
        </form>
      )}

      {paso === 'foto' && conexion && (
        <div className="space-y-3 rounded-xl bg-white p-4 shadow-sm">
          <p className="text-sm">Medidor <b>{nombreMedidor(conexion)}</b>. Saque una foto donde se lean bien los números.</p>
          {(conexion.leida || yaLocal) && <Aviso tipo="error">Este medidor ya tiene una lectura en el período. Si continúa, la nueva quedará en revisión.</Aviso>}
          <label className="boton-primario block w-full cursor-pointer py-4 text-center text-lg">
            📷 Tomar foto del medidor
            <input type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => void elegirFoto(e.target.files?.[0], 'camara')} />
          </label>
          {permiteGaleria && (
            <label className="boton-secundario block w-full cursor-pointer text-center">
              Elegir de la galería
              <input type="file" accept="image/*" className="hidden" onChange={(e) => void elegirFoto(e.target.files?.[0], 'galeria')} />
            </label>
          )}
          <button className="text-sm text-koape-gris underline" onClick={otra}>Cancelar</button>
        </div>
      )}

      {paso === 'lectura' && conexion && foto && (
        <form onSubmit={confirmar} className="space-y-4">
          <div className="rounded-xl bg-white p-4 shadow-sm">
            <img src={foto.url} alt="Foto del medidor" className="mb-3 max-h-56 w-full rounded-lg bg-koape-fondo object-contain" />
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <div className="col-span-2"><dt className="etiqueta">Titular</dt><dd className="text-base font-bold">{conexion.titular}</dd></div>
              <div className="col-span-2"><dt className="etiqueta">Dirección</dt><dd>{conexion.direccion || '—'}{conexion.barrio ? ` · ${conexion.barrio}` : ''}</dd></div>
              <div><dt className="etiqueta">Conexión</dt><dd className="font-semibold">{conexion.conexion}</dd></div>
              <div><dt className="etiqueta">Medidor</dt><dd className="font-semibold">{nombreMedidor(conexion)}</dd></div>
              <div className="col-span-2"><dt className="etiqueta">Lectura anterior</dt><dd className="text-lg font-bold">{fmt(conexion.lectura_anterior)} <span className="text-xs font-normal text-koape-gris">{conexion.fecha_lectura_anterior ?? ''}</span></dd></div>
            </dl>
            {conexion.tiene_foto_vivienda && enRed && (
              <details className="mt-3 text-sm">
                <summary className="cursor-pointer text-koape-rojo">Ver foto de la vivienda</summary>
                <FotoPrivada ruta={`cobrador/recorridos/${encodeURIComponent(code)}/foto-vivienda/${conexion.conexion}/`} alt="Vivienda" className="mt-2 max-h-56 w-full rounded-lg object-cover" />
              </details>
            )}
          </div>
          <div className="space-y-3 rounded-xl bg-white p-4 shadow-sm">
            <label className="block">
              <span className="etiqueta">Lectura actual{conexion.unidad === 'm3' ? ' (m³)' : ''}</span>
              <input className="campo py-3 text-center text-3xl font-extrabold" inputMode="decimal" autoFocus value={valor} onChange={(e) => setValor(e.target.value)} />
            </label>
            {estimado !== null && (
              <p className={`text-sm ${estimado < 0 ? 'font-semibold text-rose-700' : 'text-koape-gris'}`}>
                {estimado < 0 ? 'Es menor que la anterior: explique en el comentario (quedará en revisión).' : `Consumo estimado: ${fmt(estimado)} (lo confirma el servidor).`}
              </p>
            )}
            <label className="block">
              <span className="etiqueta">Comentario (opcional)</span>
              <textarea className="campo" value={comentario} onChange={(e) => setComentario(e.target.value)} placeholder="Ej. medidor empañado, perro suelto…" />
            </label>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <label className="boton-secundario cursor-pointer">
                + Foto adicional ({adicionales.length}/3)
                <input type="file" accept="image/*" capture="environment" className="hidden" disabled={adicionales.length >= 3} onChange={(e) => void agregarAdicional(e.target.files?.[0])} />
              </label>
            </div>
            <p className={`text-xs ${posicion ? 'text-emerald-700' : 'text-amber-700'}`}>
              {posicion ? `📍 Ubicación lista (±${Math.round(posicion.precision)} m)` : errorGps || 'Buscando ubicación GPS…'}
            </p>
            <button className="boton-primario w-full py-3 text-lg" disabled={guardando || !posicion || !valor.trim()}>
              {guardando ? 'Guardando…' : 'Confirmar lectura'}
            </button>
            {!posicion && <p className="text-center text-xs text-koape-gris">Sin ubicación GPS no se puede confirmar.</p>}
          </div>
        </form>
      )}

      {paso === 'listo' && resultado && (
        <div className="space-y-3 rounded-xl bg-white p-4 shadow-sm">
          {resultado.comprobante ? (
            <>
              <p className="text-lg font-bold text-emerald-700">✓ Lectura registrada</p>
              <p className="text-sm">Comprobante <b>{resultado.comprobante}</b>{resultado.consumo ? <> · consumo <b>{fmt(resultado.consumo)}</b></> : null}</p>
              {enRed && <button className="boton-secundario w-full py-3 text-lg" onClick={() => { const c = resultado.comprobante; if (c) void abrirTicket(api, c).then(setError) }}>🧾 Imprimir ticket</button>}
              {resultado.estado === 'revision' && <Aviso tipo="error">Quedó en revisión: {resultado.motivo_revision}. La oficina la va a revisar.</Aviso>}
              <Deudas deudas={resultado.deudas} />
            </>
          ) : resultado.estado === 'error' ? (
            <>
              <p className="text-lg font-bold text-rose-700">La lectura fue rechazada</p>
              <p className="text-sm">{resultado.error}</p>
              <p className="text-xs text-koape-gris">Quedó en «Lecturas» de este teléfono: puede reintentar o descartarla.</p>
            </>
          ) : (
            <>
              <p className="text-lg font-bold text-amber-700">Guardada en el teléfono</p>
              <p className="text-sm">Sin conexión: se enviará sola cuando vuelva la señal. No borre los datos del navegador.</p>
            </>
          )}
          <button className="boton-primario w-full py-3 text-lg" onClick={otra}>Tomar otra lectura</button>
          <Link className="boton-secundario block w-full text-center" to={`/cobrador/r/${code}`}>Volver al recorrido</Link>
        </div>
      )}
    </div>
  )
}

const gsCob = (v: string) => `Gs. ${Number(v).toLocaleString('es-PY', { maximumFractionDigits: 0 })}`

/** Paso 6: lo que debe la conexión (solo informativo: en v1 el cobrador no cobra). */
function Deudas({ deudas }: { deudas?: Operacion['deudas'] }) {
  if (!deudas || !deudas.disponible) return null
  const total = [...deudas.pendientes_de_facturar.map((p) => Number(p.total)), ...deudas.facturas.map((f) => Number(f.saldo))].reduce((a, b) => a + b, 0)
  if (!deudas.pendientes_de_facturar.length && !deudas.facturas.length) return <p className="text-sm text-emerald-700">{deudas.mensaje || 'Sin deudas pendientes.'}</p>
  return (
    <div className="rounded-lg bg-amber-50 p-3 text-sm">
      <p className="font-bold">Deuda de la conexión: {gsCob(String(total))}</p>
      <ul className="mt-1 space-y-0.5">
        {deudas.pendientes_de_facturar.map((p) => <li key={p.liquidacion}>Consumo {p.periodo}: {gsCob(p.total)} (a facturar en la oficina)</li>)}
        {deudas.facturas.map((f) => <li key={f.numero}>Factura {f.numero}: saldo {gsCob(f.saldo)}{f.dias_mora > 0 ? <b className="text-rose-700"> · {f.dias_mora} días de atraso</b> : null}</li>)}
      </ul>
      <p className="mt-1 text-xs text-koape-gris">Se paga en la oficina.</p>
    </div>
  )
}
