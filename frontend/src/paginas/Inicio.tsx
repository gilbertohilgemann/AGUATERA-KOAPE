import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import type { ResumenPadron } from '../api/tipos'
import { useSesion } from '../sesion/ContextoSesion'
import { PanelIndicadores } from './informes/Informes'
import { GRUPOS } from './Marco'

function Indicador({ titulo, valor, enlace, alerta = false }: { titulo: string; valor: number; enlace?: string; alerta?: boolean }) {
  const contenido = (
    <>
      <p className="etiqueta">{titulo}</p>
      <p className={`font-titulo text-3xl font-extrabold ${alerta && valor > 0 ? 'text-koape-rojo' : ''}`}>{valor}</p>
    </>
  )
  return enlace ? <Link to={enlace} className="tarjeta p-4 transition hover:border-koape-magenta">{contenido}</Link> : <div className="tarjeta p-4">{contenido}</div>
}

export function Inicio() {
  const { api, datos, puede } = useSesion()
  const [resumen, setResumen] = useState<ResumenPadron | null>(null)
  const accesos = GRUPOS.flatMap((g) => g.items).filter(
    (i) => i.ruta && i.ruta !== 'cuenta' && (!i.permisos || i.permisos.some((p) => puede(p))),
  )

  const vePadron = puede('padron.consultar') // booleano: `puede` cambia en cada render y no sirve de dependencia

  useEffect(() => {
    if (vePadron) api.get<ResumenPadron>('padron/resumen/').then((r) => setResumen(r.data)).catch(() => setResumen(null))
  }, [api, vePadron])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold">Hola, {datos.usuario.nombre || datos.usuario.usuario}</h1>
        <p className="text-sm text-koape-gris">{datos.institucion.nombre} · {datos.institucion.codigo}</p>
      </div>
      {resumen && (
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Indicador titulo="Clientes" valor={resumen.clientes} enlace="/panel/clientes" />
          <Indicador titulo="Conexiones" valor={resumen.conexiones} enlace="/panel/conexiones" />
          <Indicador titulo="Activas" valor={resumen.conexiones_por_estado.activa} />
          <Indicador titulo="Suspendidas" valor={resumen.conexiones_por_estado.suspendida} />
          <Indicador titulo="Sin ubicación" valor={resumen.sin_ubicacion} alerta />
          <Indicador titulo="Sin medidor" valor={resumen.sin_medidor} alerta />
        </div>
      )}
      <PanelIndicadores omitir={resumen ? ['Padrón'] : []} />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {accesos.map((i) => (
          <Link key={i.ruta} to={`/panel/${i.ruta}`} className="tarjeta p-5 transition hover:border-koape-magenta">
            <p className="font-titulo text-lg font-bold">{i.texto}</p>
          </Link>
        ))}
      </div>
      <p className="text-xs text-koape-gris">
        Sesión válida hasta {new Date(datos.sesion_vence_en).toLocaleString('es-PY')}.
      </p>
    </div>
  )
}
