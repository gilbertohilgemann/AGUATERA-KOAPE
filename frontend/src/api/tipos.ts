export interface DatosSesion {
  usuario: {
    id: number
    usuario: string
    nombre: string
    apellido: string
    correo: string
    es_admin_institucion: boolean
    debe_cambiar_contrasena: boolean
  }
  institucion: {
    codigo: string
    nombre: string
    estado: string
    logo: string | null
    lecturas_permite_galeria: boolean
  }
  permisos: string[]
  sesion_vence_en: string
}

export interface Pagina<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface Usuario {
  id: number
  usuario: string
  nombre: string
  apellido: string
  correo: string
  activo: boolean
  es_admin_institucion: boolean
  roles: number[]
  ultimo_ingreso: string | null
  debe_cambiar_contrasena: boolean
  bloqueado: boolean
}

export interface Rol {
  id: number
  Code: string
  nombre: string
  descripcion: string
  permisos: string[]
  activo: boolean
  cantidad_usuarios: number
}

export interface Permiso {
  id: number
  codigo: string
  descripcion: string
  modulo: string
}

export interface Institucion {
  codigo: string
  nombre: string
  ruc: string
  direccion: string
  telefono: string
  correo: string
  contacto: string
  logo: string | null
  estado: string
  estado_nombre: string
  zona_horaria: string
  configuracion_regional: string
  modalidad_facturacion: string
  modalidad_facturacion_nombre: string
  lecturas_permite_galeria: boolean
  dias_vencimiento_credito: number
  aplicacion_pagos: 'manual' | 'automatica'
  portal_abonados: boolean
  creado_en: string
}

export interface RegistroAuditoria {
  id: number
  ocurrido_en: string
  usuario_nombre: string
  accion: string
  entidad: string
  entidad_id: string
  resultado: 'exito' | 'fallo'
  motivo: string
  antes: Record<string, unknown> | null
  despues: Record<string, unknown> | null
  detalle: Record<string, unknown>
  ip: string | null
  id_solicitud: string
}

// --- Fase 2: padrón y territorio -------------------------------------------------------------

export type Poligono = { type: 'Polygon'; coordinates: number[][][] } | { type: 'MultiPolygon'; coordinates: number[][][][] }

// Convención: ningún registro se identifica por su id interno. Los maestros se identifican y se
// referencian por su `Code` (texto que carga el usuario, único en la institución).

export interface Zona {
  Code: string
  nombre: string
  color: string
  poligono: Poligono | null
  observaciones: string
  activa: boolean
  cantidad_barrios: number
}

export interface Barrio {
  Code: string
  zona: string
  zona_nombre: string
  nombre: string
  poligono: Poligono | null
  observaciones: string
  activo: boolean
}

export interface Cliente {
  Code: string
  nombre: string
  tipo_persona: 'fisica' | 'juridica'
  documento: string
  telefono: string
  correo: string
  direccion_referencia: string
  observaciones: string
  estado: 'activo' | 'inactivo' | 'archivado'
  estado_nombre: string
  fecha_alta: string
  cantidad_conexiones: number
}

export type EstadoConexion = 'en_instalacion' | 'pendiente_ubicacion' | 'activa' | 'suspendida' | 'desconectada' | 'archivada'

export interface ConexionResumen {
  Code: string
  cliente: string
  cliente_nombre: string
  direccion: string
  barrio: string | null
  barrio_nombre: string
  zona: string | null
  zona_nombre: string
  latitud: string | null
  longitud: string | null
  estado: EstadoConexion
  estado_nombre: string
  medidor_actual: string | null
  medidor_numero: string
}

export interface Instalacion {
  conexion: string
  medidor: string
  medidor_numero: string
  fecha_instalacion: string
  lectura_inicial: string
  fecha_retiro: string | null
  lectura_retiro: string | null
  motivo_retiro: string
  instalado_por_nombre: string
  retirado_por_nombre: string
  observaciones: string
}

export interface Titularidad {
  cliente: string
  cliente_nombre: string
  desde: string
  hasta: string | null
  motivo: string
}

export interface ConexionDetalle extends ConexionResumen {
  tarifa: string | null
  tarifa_nombre: string
  metodo_ubicacion: 'sin_ubicacion' | 'gps' | 'mapa' | 'manual'
  metodo_ubicacion_nombre: string
  precision_metros: number | null
  fecha_instalacion: string | null
  observaciones: string
  tiene_foto_vivienda: boolean
  instalaciones: Instalacion[]
  titularidades: Titularidad[]
  transiciones: { estado: EstadoConexion; nombre: string }[]
}

export interface Medidor {
  Code: string
  numero: string
  marca: string
  modelo: string
  unidad: string
  lectura_maxima: string | null
  estado: 'disponible' | 'instalado' | 'retirado' | 'danado' | 'baja'
  estado_nombre: string
  observaciones: string
  conexion_actual: string | null
}

export interface PuntoMapa {
  Code: string
  lat: number
  lon: number
  estado: EstadoConexion
  estado_nombre: string
  titular: string
  direccion: string
  barrio: string
  zona: string | null
  medidor: string | null
  tiene_foto: boolean
  /** Solo para quien puede consultar cobranzas o facturas (D50). */
  deuda?: 'al_dia' | 'con' | 'morosa'
}

export interface DatosMapa {
  zonas: { Code: string; nombre: string; color: string; poligono: Poligono | null; activa: boolean }[]
  barrios: { Code: string; nombre: string; zona: string; color: string; poligono: Poligono | null; activo: boolean }[]
  conexiones: PuntoMapa[]
  sin_ubicacion: number
  total: number
}

// --- Numeración de facturas y notas de crédito (SerNr) -----------------------------------------

export type TipoDocumento = 'factura' | 'nota_credito'

export interface RangoNumeracion {
  Code: string
  punto: string
  punto_prefijo: string
  tipo_documento: TipoDocumento
  tipo_documento_nombre: string
  timbrado: string
  desde: number
  hasta: number
  vigencia_desde: string | null
  vigencia_hasta: string | null
  activo: boolean
  observaciones: string
  en_uso: boolean
  agotado: boolean
}

export interface PuntoExpedicion {
  Code: string
  establecimiento: string
  punto: string
  prefijo: string
  nombre: string
  direccion: string
  activo: boolean
  observaciones: string
  rangos: RangoNumeracion[]
}

export interface ResumenPadron {
  clientes: number
  conexiones: number
  conexiones_por_estado: Record<EstadoConexion, number>
  sin_ubicacion: number
  sin_medidor: number
  medidores_disponibles: number
}

// --- Fase 3: recorridos y lecturas ----------------------------------------------------------------

export type EstadoRecorrido = 'planificado' | 'abierto' | 'cerrado' | 'anulado'

export interface Avance {
  total: number
  leidas: number
  confirmadas: number
  en_revision: number
  pendientes: number
}

export interface Recorrido {
  Code: string
  nombre: string
  periodo: string
  estado: EstadoRecorrido
  estado_nombre: string
  fecha_desde: string | null
  fecha_hasta: string | null
  observaciones: string
  cobradores: { usuario: string; nombre: string; activa: boolean; iniciado_en: string | null; finalizado_en: string | null }[]
  avance: Avance
}

export interface ParadaRecorrido {
  orden: number
  conexion: string
  titular: string
  direccion: string
  barrio: string
  estado_conexion: string
  medidor: string | null
  medidor_numero: string
  lectura: { comprobante: string; estado: EstadoLectura; estado_nombre: string } | null
}

export type EstadoLectura = 'confirmada' | 'requiere_revision' | 'anulada'

export interface Lectura {
  comprobante: string
  id_operacion: string
  periodo: string
  recorrido: string
  conexion: string
  titular: string
  direccion: string
  medidor: string
  medidor_numero: string
  lectura_anterior: string
  fecha_lectura_anterior: string
  origen_anterior: 'lectura' | 'instalacion'
  lectura_actual: string
  consumo: string | null
  capturada_en: string
  sincronizada_en: string
  cobrador: string
  cobrador_nombre: string
  latitud: string
  longitud: string
  precision_metros: number | null
  distancia_metros: number | null
  foto_origen: 'camara' | 'galeria'
  estado: EstadoLectura
  estado_nombre: string
  motivo_revision: string
  motivo_revision_nombre: string
  comentario: string
  resuelta_por: string | null
  resuelta_en: string | null
  resolucion: string
  fotos: { n: number; principal: boolean; origen: string }[]
}

export interface DeudasLectura {
  disponible: boolean
  pendientes_de_facturar: { liquidacion: string; periodo: string; total: string }[]
  facturas: { numero: string; fecha_emision: string; fecha_vencimiento: string | null; importe: string; pagado: string; saldo: string; dias_mora: number }[]
  mensaje: string
}

/** Lo que el teléfono descarga para trabajar sin conexión. */
export interface ConexionPaquete {
  orden: number
  conexion: string
  titular: string
  direccion: string
  barrio: string
  lat: number | null
  lon: number | null
  tiene_foto_vivienda: boolean
  medidor: string | null
  /** Número grabado en el medidor (letras y números); vacío si no se cargó. */
  medidor_numero: string
  unidad: string | null
  lectura_maxima: string | null
  lectura_anterior: string | null
  fecha_lectura_anterior: string | null
  leida: { comprobante: string; estado: EstadoLectura } | null
}

export interface PaqueteRecorrido {
  recorrido: Recorrido
  institucion: { nombre: string; permite_galeria: boolean }
  conexiones: ConexionPaquete[]
}

// --- Fase 4: tarifas y liquidaciones -----------------------------------------------------------------

export type TipoConcepto = 'minimo' | 'excedente' | 'tramo' | 'por_m3' | 'fijo' | 'porcentaje'
export type TasaIva = '10' | '5' | 'exento'

export interface ConceptoTarifa {
  orden: number
  nombre: string
  tipo: TipoConcepto
  tipo_nombre?: string
  cantidad: string | null
  desde: string | null
  hasta: string | null
  precio: string | null
  porcentaje: string | null
  iva: TasaIva
  iva_nombre?: string
}

export interface VersionTarifa {
  vigente_desde: string
  observaciones: string
  conceptos: ConceptoTarifa[]
  usada: boolean
}

export interface Tarifa {
  Code: string
  nombre: string
  descripcion: string
  por_defecto: boolean
  activa: boolean
  versiones: VersionTarifa[]
  cantidad_conexiones: number
}

export interface LineaCalculo {
  concepto: string
  tipo: TipoConcepto
  cantidad: string
  precio: string
  importe: string
  iva: TasaIva
  iva_nombre?: string
}

export interface ResultadoCalculo {
  version?: string
  lineas: LineaCalculo[]
  subtotal_exento: string
  subtotal_iva5: string
  subtotal_iva10: string
  iva5: string
  iva10: string
  total: string
}

export interface Liquidacion extends ResultadoCalculo {
  numero: string
  lectura: string
  conexion: string
  titular: string
  periodo: string
  tarifa: string
  tarifa_nombre: string
  version: string
  consumo: string
  estado: 'vigente' | 'anulada'
  estado_nombre: string
  motivo_anulacion: string
  anulada_por: string | null
  anulada_en: string | null
  creado_en: string
}

export interface ResumenLiquidaciones {
  cantidad: number
  consumo: string | number
  exento: string | number
  gravado5: string | number
  gravado10: string | number
  iva5: string | number
  iva10: string | number
  total: string | number
  sin_liquidar: number
}

// --- Fase 5: facturación ------------------------------------------------------------------------------

export interface PendienteFacturar {
  numero: string
  periodo: string
  conexion: string
  direccion: string
  tarifa: string
  lectura: string
  consumo: string
  total: string
}

export interface PendientesCliente {
  cliente: { Code: string; nombre: string; documento: string; direccion: string }
  pendientes: PendienteFacturar[]
  modalidad: 'no_configurada' | 'autoimpresa' | 'electronica'
  dias_vencimiento_credito: number
  puntos: { Code: string; prefijo: string; nombre: string }[]
  formas_pago: { Code: string; nombre: string; requiere_referencia: boolean }[]
}

export interface LineaFactura {
  descripcion: string
  tipo: string
  cantidad: string
  precio_unitario: string
  iva: '10' | '5' | 'exento'
  importe: string
  importe_iva: string
  total_linea: string
  liquidacion: string
}

export interface Factura {
  referencia: string
  numero: string
  punto: string
  timbrado: string
  modalidad: 'autoimpresa' | 'electronica'
  cliente: string
  cliente_nombre: string
  cliente_documento: string
  cliente_direccion: string
  condicion: 'contado' | 'credito'
  condicion_nombre: string
  fecha_emision: string
  fecha_vencimiento: string | null
  subtotal_exento: string
  subtotal_iva5: string
  subtotal_iva10: string
  iva5: string
  iva10: string
  total: string
  estado: 'en_tramite' | 'emitida' | 'rechazada' | 'anulada'
  estado_nombre: string
  observaciones: string
  cdc: string
  emitida_por: string
  creado_en: string
  anulada_por: string | null
  anulada_en: string | null
  motivo_anulacion: string
  liquidaciones: { numero: string; periodo: string; conexion: string; importe: string; estado: string }[]
  lineas: LineaFactura[]
  electronica: { estado: string; estado_nombre: string; intentos: number; proveedor: string; ultimo_error: string } | null
  pagado: string
  saldo: string
  estado_cobro: '' | 'pagada' | 'parcial' | 'pendiente' | 'vencida'
  pagos: { pago: string; fecha_hora: string; importe: string; forma_pago: string; referencia_externa: string; origen: 'contado' | 'recibo'; recibo: string | null; estado: 'vigente' | 'revertida'; usuario: string }[]
}

// --- Fase 6: pagos y recibos ---------------------------------------------------------------------------

export interface FormaPago {
  Code: string
  nombre: string
  tipo: 'efectivo' | 'transferencia' | 'pos' | 'otro'
  tipo_nombre: string
  requiere_referencia: boolean
  orden: number
  activa: boolean
}

export interface FacturaConSaldo {
  referencia: string
  numero: string
  fecha_emision: string
  fecha_vencimiento: string | null
  total: string
  pagado: string
  saldo: string
  estado_cobro: string
}

export interface EstadoCuenta {
  cliente: { Code: string; nombre: string; documento: string }
  facturas: FacturaConSaldo[]
  total_saldo: string
  aplicacion_pagos: 'manual' | 'automatica'
  formas_pago: FormaPago[]
}

export interface AplicacionRecibo {
  factura: string
  numero: string
  fecha_emision: string
  fecha_vencimiento: string | null
  total: string
  saldo_anterior: string
  importe: string
  saldo_posterior: string
  estado: 'vigente' | 'revertida'
}

export interface Recibo {
  numero: string
  fecha_hora: string
  cliente: string
  cliente_nombre: string
  cliente_documento: string
  importe: string
  forma_pago: string
  referencia_externa: string
  observaciones: string
  cobrado_por: string
  saldo_restante: string
  estado: 'emitido' | 'anulado'
  estado_nombre: string
  anulado_por: string | null
  anulado_en: string | null
  motivo_anulacion: string
  aplicaciones: AplicacionRecibo[]
}

export interface Pago {
  referencia: string
  fecha_hora: string
  cliente: string
  cliente_nombre: string
  importe: string
  forma_pago: string
  tipo_forma: string
  referencia_externa: string
  origen: 'contado' | 'recibo'
  origen_nombre: string
  estado: 'confirmado' | 'revertido'
  estado_nombre: string
  cobrado_por: string
  motivo_reversion: string
  recibo: string | null
  aplicaciones: AplicacionRecibo[]
}

// --- Fase 7: caja y gastos -----------------------------------------------------------------------------

export interface Caja {
  Code: string
  nombre: string
  activa: boolean
  abierta_por: string | null
}

export interface FilaResumenCaja {
  forma_pago: string
  nombre: string
  tipo: string
  saldo_inicial: string
  ingresos: string
  egresos: string
  esperado: string
}

export interface SesionCaja {
  referencia: string
  caja: string
  caja_nombre: string
  responsable: string
  abierta_en: string
  saldo_inicial: string
  estado: 'abierta' | 'en_revision' | 'cerrada'
  estado_nombre: string
  cerrada_en: string | null
  observaciones_cierre: string
  revisada_por: string | null
  revisada_en: string | null
  comentario_revision: string
  resumen: FilaResumenCaja[]
  declaraciones: { forma_pago: string; nombre: string; esperado: string; declarado: string; diferencia: string }[]
}

export interface MiCaja {
  sesion: SesionCaja | null
  cajas_libres: { Code: string; nombre: string }[]
}

export interface MovimientoCaja {
  fecha_hora: string
  tipo: 'ingreso' | 'egreso'
  origen: string
  origen_nombre: string
  forma_pago: string
  tipo_forma: string
  importe: string
  descripcion: string
  usuario: string | null
  pago: string | null
  recibo: string | null
  gasto: string | null
  revertido: boolean
}

export interface CategoriaGasto {
  Code: string
  nombre: string
  activa: boolean
}

export interface Gasto {
  referencia: string
  fecha: string
  motivo: string
  importe: string
  categoria: string
  categoria_nombre: string
  forma_pago: string
  forma_pago_nombre: string
  numero_comprobante: string
  beneficiario: string
  responsable: string
  observaciones: string
  sesion: string | null
  estado: 'registrado' | 'confirmado' | 'anulado'
  estado_nombre: string
  registrado_por: string
  creado_en: string
  confirmado_por: string | null
  confirmado_en: string | null
  anulado_por: string | null
  anulado_en: string | null
  motivo_anulacion: string
  boleta: { numero: string; fecha: string } | null
  adjuntos: { codigo: string; tipo: string; tipo_nombre: string; es_pdf: boolean; subido_por: string; creado_en: string }[]
}

// --- Fase 8: informes e integraciones ------------------------------------------------------------------

export interface InformeCatalogo {
  codigo: string
  titulo: string
  grupo: string
  definicion: string
  filtros: string[]
  agrupaciones: { valor: string; texto: string }[]
}

export interface ColumnaInforme {
  clave: string
  titulo: string
  tipo: 'texto' | 'numero' | 'gs' | 'decimal' | 'porcentaje' | 'fecha'
}

export interface DatosInforme {
  codigo: string
  titulo: string
  definicion: string
  columnas: ColumnaInforme[]
  filas: Record<string, string | number>[]
  totales: Record<string, string> | null
  filtros: Record<string, string>
}

export interface IndicadorPanel {
  titulo: string
  valor: string
  tipo: 'numero' | 'gs' | 'm3' | 'texto'
  definicion: string
  enlace: string
  alerta: boolean
}

export interface SeccionPanel {
  titulo: string
  indicadores: IndicadorPanel[]
}

export interface CredencialIntegracion {
  prefijo: string
  nombre: string
  permisos: string[]
  limite_por_minuto: number
  expira_en: string | null
  activa: boolean
  creada_por: string
  creado_en: string
  revocada_por: string | null
  revocada_en: string | null
  motivo_revocacion: string
  ultimo_uso_en: string | null
  usos_30_dias: number
  clave?: string
}
