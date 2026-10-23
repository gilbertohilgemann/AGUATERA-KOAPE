# Koape Aguateras

Plataforma web multiinstitucional para administrar aguateras, juntas de saneamiento y prestadores
comunitarios de agua potable: padrón, conexiones, medidores, lecturas, facturación, cobranzas, caja,
gastos y mapas. Desarrollado por **Koape Sistemas EAS**.

- Especificación: `informacion-tecnica.txt` · Convenciones: `Convenciones-de-Proyecto.txt`
- Arquitectura y plan por fases: `docs/PROPUESTA_ARQUITECTURA.md`
- Decisiones técnicas: `docs/DECISIONES.md` · API: `docs/API.md`

## Estado

Pruebas automáticas del backend: **255**, todas pasan con SQLite y con PostgreSQL 16 (con PostgreSQL se omiten 3
pruebas del respaldo propias de SQLite).

| Fase | Contenido | Estado |
|---|---|---|
| 1. Base | Instituciones, ingreso con código institucional, usuarios/roles/permisos, aislamiento, auditoría, migración de base, backup, manual, instaladores | **Hecha** |
| 2. Padrón y mapa | Clientes, conexiones (estados, titulares, ubicación, foto privada), medidores e instalaciones, zonas y barrios con polígonos, mapa Leaflet | **Hecha** |
| Convención de claves | `Code` en los maestros (lo carga el usuario, sin autonumérico visible) · puntos de expedición y rangos de numeración para el `SerNr` de facturas y notas de crédito | **Hecha** |
| 3. Recorridos y lecturas | Recorridos mensuales (armado, orden, cobradores, avance), aplicación del cobrador instalable (PWA) con foto y GPS obligatorios, trabajo sin conexión y sincronización sin duplicados, revisión de excepciones en la oficina, comprobante PDF, filtros del mapa por lectura y recorrido | **Hecha** |
| 4. Tarifas y liquidaciones | Tarifas por tipo de conexión con versiones por vigencia; conceptos configurables (consumo mínimo, excedente, tramos, por m³, cargo fijo, porcentajes como la tasa ERSSAN) con IVA 10/5/exento por concepto; liquidación automática al confirmarse la lectura con instantánea reproducible; simulador | **Hecha** |
| 5. Facturación | Factura en caja cuando el usuario viene a pagar: una o varias liquidaciones enteras, contado o crédito (vencimiento configurable); numeración por punto y timbrado; PDF autoimpreso; anulación que libera las liquidaciones; capa de factura electrónica desacoplada (sin proveedor todavía) con idempotencia y consulta tras cortes; deudas visibles para el cobrador | **Hecha** |
| 6. Pagos y recibos | Contado: el pago se registra al emitir la factura (con forma de pago). Crédito: recibos con pagos parciales, un pago a varias facturas, reparto manual o automático (vencida más antigua) según la institución; saldos y estado de cobro derivados; reintentos sin duplicar; anulación de recibos que revierte el pago y conserva el original; formas de pago configurables; historial de cobros; recibo PDF con importe en letras | **Hecha** |
| 7. Caja y gastos | Sesión de caja por cajero (obligatoria para cobrar), cada cobro y gasto entra una sola vez, saldos separados por forma de pago, cierre con lo contado y diferencias en revisión, reversiones compensatorias que no tocan sesiones cerradas, arqueo PDF; gastos referenciales con categorías, comprobantes adjuntos, boleta interna PDF numerada y confirmación por permiso | **Hecha** |
| 8. Informes e integración | Panel de indicadores con definiciones; 11 informes (padrón, lecturas, consumo, liquidaciones, facturado, saldos, antigüedad de deuda, recaudación, gastos, cajas, factura electrónica) con filtros y exportación a Excel/CSV según permisos; credenciales de integración por institución (solo lectura, revocables, con vencimiento, límite por minuto y registro de solicitudes); API documentada | **Hecha** |
| Recuperar contraseña y filtros de deuda | «¿Olvidó su contraseña?» con código por correo para el personal; padrón y mapa filtran y colorean por con deuda, al día y morosa (definiciones explícitas) | **Hecha** |
| Portal de abonados | Una cuenta por persona (documento) para consultar en todas las instituciones con portal: activación con PIN al correo del padrón, contraseña propia, deuda, facturas y recibos PDF, pagos, lecturas con foto y conexiones (solo lectura). Cobrador: búsqueda por orden o número del medidor y mapa del recorrido (verde leídos, rojo faltantes) | **Hecha** |

## Stack

| Capa | Stack |
|---|---|
| Backend | Django 5.2 + Django REST Framework, apps separadas por dominio, reglas en `servicios.py` |
| Frontend | React 18 + Vite + TypeScript + Tailwind CSS v4, axios |
| Base de datos | SQLite en desarrollo · PostgreSQL en producción (migración sin pérdida desde el panel) |

```
backend/
  configuracion/      settings, urls, wsgi
  comun/              base institucional de modelos, errores, middleware, cifrado, pruebas de aislamiento
  apps/plataforma/    Institucion (alta, estados), chequeo de seguridad
  apps/identidad/     Usuario, Rol, Permiso, TokenSesion, ingreso
  apps/auditoria/     RegistroAuditoria (solo inserción)
  apps/territorio/    Zona, Barrio (polígonos GeoJSON)
  apps/padron/        Cliente, Conexion, TitularidadConexion, Medidor, InstalacionMedidor, mapa
  apps/migracion_bd/  panel «sin tabla» SQLite ⇄ PostgreSQL
  apps/respaldo/      panel «sin tabla» de backup .zip + restauración
  apps/manual/        manual de la plataforma en el admin
frontend/src/
  api/ sesion/ componentes/ paginas/ (padron/) mapa/ utilidades/
scripts/              funciones comunes de los instaladores + servidor Fedora
```

## Instalación en Linux (desarrollo o PC local)

```bash
./install.sh            # una vez, o de nuevo al actualizar código
./start.sh start        # stop | status | restart | update | logs | respaldo | respaldo-programar | verificar <zip> | restaurar <zip> | seguridad | https | datos-prueba
```

`install.sh` revisa dependencias del sistema y **pide permiso** antes de instalar algo, arma `backend/venv` y
`node_modules`, genera `SECRET_KEY`, busca puertos libres (9006 API, 5206 web; si están ocupados por otra cosa
no la toca y usa el siguiente), deja la base en SQLite, crea/restablece el administrador fijo de la plataforma
y pregunta si crear las instituciones de demostración y si activar el arranque automático (systemd).

## Instalación en Windows

```
install.bat             (doble clic)
start.bat               start | stop | status | restart | logs | update | red | red-quitar | https | respaldo | respaldo-programar | verificar ARCHIVO | restaurar ARCHIVO | seguridad | datos-prueba
```

`python manage.py cargar_demos_itapua` crea dos aguateras de demostración, **DEMO-ENC** (Encarnación) y **DEMO-CAM**
(Cambyretá), cada una con 20 abonados ubicados en su zona, medidores, tres meses de lecturas, facturas contado y a
crédito con pagos y recibos, y deuda pendiente. Usuarios: `admin`, `cobrador1` y `cajero1`, los tres con
`Acceso*2026`. Es idempotente. El ingreso muestra los botones «Acceso como demo» de DEMO-ENC mientras `frontend/.env` tenga
`VITE_ACCESO_DEMO=1` (para un sistema real, bórrelo y recompile).

`datos-prueba` carga en la institución DEMO un escenario completo para probar (8 clientes ubicados, tarifa,
numeración de facturas, dos meses ya leídos listos para facturar y el recorrido del mes abierto para el celular) y
los usuarios `cobrador1` y `cajero1` (contraseña `Prueba.Koape.2026`). Solo funciona en instituciones DEMO vacías.

`start.bat` es un lanzador de una línea; la lógica vive en `start.ps1`. Los procesos corren en segundo plano
sin ventanas; al detener se mata el árbol completo (`taskkill /T /F`).

## Servidor (VPS Fedora Cloud · aguateras.koapesystem.com)

Guía completa paso a paso (clave de despliegue de GitHub, instalación, correo, respaldos): **`docs/DESPLIEGUE.md`**.

```bash
# como root, con el proyecto en /home/webuser/AGUATERA-KOAPE
bash scripts/servidor/instalar_fedora.sh aguateras.koapesystem.com correo@koapesystem.com
bash scripts/servidor/actualizar.sh          # git pull + dependencias + migraciones + frontend
bash scripts/servidor/https.sh               # reintenta el certificado cuando el DNS ya apunta al servidor
bash scripts/servidor/restaurar.sh <zip>
bash scripts/servidor/configurar_correo.sh   # SMTP para el PIN del portal y recuperar contraseñas
```

El instalador agrega un sitio al servidor web que ya exista (nginx, Caddy o Apache) sin tocar los demás,
configura PostgreSQL (si ya existe lo reutiliza, creando solo su usuario y su base), el servicio systemd del
backend (waitress), el respaldo diario (03:20) y HTTPS con Let's Encrypt.

## Accesos iniciales

| Qué | Dónde | Usuario / contraseña |
|---|---|---|
| Panel de la plataforma | `http://localhost:9006/admin/` | `admin` / `Koape.Admin.2026` (en `backend/.env`; en el servidor se genera una aleatoria) |
| Sistema (instituciones demo) | `http://localhost:5206/` | código `DEMO` o `DEMO2` · `admin` / `Demo.Koape.2026` |

⚠ Cambie la contraseña del administrador de la plataforma apenas ingrese. Al primer ingreso de un usuario de
institución el sistema obliga a cambiar la contraseña.

## Modelos de datos

| Modelo | App | Descripción |
|---|---|---|
| `Institucion` | plataforma | Aguatera o junta. Código único (no se cambia), datos fiscales y de contacto, estado (activa/suspendida/archivada), zona horaria, modalidad de facturación (la define la plataforma). Nunca se borra. |
| `Usuario` | identidad | Modelo propio. `institucion` vacía = usuario de la plataforma. Único por `(institucion, nombre_usuario)`. Bloqueo por intentos, cambio de contraseña obligatorio. No se borra: se desactiva. |
| `Rol` | identidad | De una institución; combina permisos. `Code` y nombre únicos en la institución (el `Code` no cambia). Se desactiva, no se borra. |
| `Permiso` | identidad | Catálogo global sincronizado desde el código tras cada `migrate`. |
| `TokenSesion` | identidad | Hash del token, usuario, institución, vencimiento, revocación, IP. |
| `RegistroAuditoria` | auditoria | Solo inserción: institución, usuario, acción, entidad, antes/después, motivo, IP, id de solicitud. |
| `Secuencia` | plataforma | Numeradores **internos** por institución con bloqueo de fila. Nunca se muestran al usuario. |
| `Zona` | territorio | `Code` único en la institución, nombre, color del mapa, polígono GeoJSON. Se archiva. |
| `Barrio` | territorio | Pertenece a una zona; `Code` único, polígono opcional. Se archiva. |
| `Cliente` | padron | Titular: `Code` (lo carga el usuario), nombre, tipo de persona, documento (opcional, no es clave; se guarda también normalizado para el portal), contacto, estado. Puede tener varias conexiones. |
| `Conexion` | padron | Titular, `Code`, dirección, barrio, latitud/longitud y método de ubicación, foto de la vivienda (archivo privado), estado con transiciones definidas. |
| `TitularidadConexion` | padron | Historial de titulares (un vigente por conexión). |
| `Medidor` | padron | `Code` (identificación interna) único, **número del medidor** (el grabado en el aparato, alfanumérico, único en la institución si se carga), marca, modelo, unidad, lectura máxima (vuelta a cero), estado. |
| `InstalacionMedidor` | padron | Medidor en una conexión durante un período, con lectura inicial y de retiro. Un vigente por medidor y por conexión (restricciones de base). Las lecturas (Fase 3) apuntarán acá. |
| `PuntoExpedicion` | facturacion | `Code`, establecimiento y punto (001-001), nombre. Una institución puede tener varios. Se desactiva. |
| `RangoNumeracion` | facturacion | `Code`, punto, tipo de documento (factura / nota de crédito), timbrado, desde–hasta, vigencia. Su contador (`ultimo_usado`) es interno. Sin superposición por punto + tipo + timbrado. |
| `DocumentoNumerado` | facturacion | Base abstracta de los documentos de formulario continuo: punto, timbrado y `SerNr` único. |
| `Factura` / `LineaFactura` | facturacion | Referencia F-XXXXXXXX (interna de rutas) y número 001-001-0000001; modalidad, timbrado y vigencia, cliente (instantánea de nombre, documento y dirección), condición y vencimiento, líneas con IVA, subtotales IVA incluido, IVA 5/10, total, estado (emitida, en trámite, rechazada, anulada). No se borra. |
| `AsignacionFacturaLiquidacion` | facturacion | Liquidación facturada; una vigente por liquidación (restricción de base). Se libera al anular o rechazar. |
| `FormaPago` | cobranzas | `Code`, nombre, tipo (efectivo, transferencia, POS, otro), pide referencia, activa. Iniciales: EFECTIVO, TRANSFERENCIA, POS. |
| `Pago` | cobranzas | Dinero recibido: referencia P-XXXXXXXX, cliente, fecha y hora, importe, forma de pago y referencia, origen (factura contado o recibo), estado (confirmado / revertido con motivo), clave de idempotencia única. No se borra. |
| `AplicacionPago` | cobranzas | Cuánto de un pago va a cada factura, con el saldo anterior; vigente o revertida. El saldo de la factura se deriva de estas. |
| `Recibo` | cobranzas | Número correlativo de la institución, pago, cliente (instantánea), importe, saldo restante del cliente, estado (emitido / anulado con motivo). |
| `Caja` | caja | Ventanilla o punto de cobro (`Code`, nombre, activa). Inicial: CAJA1. |
| `SesionCaja` | caja | Turno de un cajero en una caja: referencia S-XXXXXXXX, saldo inicial en efectivo, estado (abierta / en revisión / cerrada), cierre, revisión. Una abierta por cajero y por caja (restricciones de base). |
| `MovimientoCaja` | caja | Ingreso o egreso con su ORIGEN (cobro, gasto o su reversión), forma de pago e importe; la reversión apunta al original. Un ingreso por pago y un egreso por gasto (restricciones de base). |
| `DeclaracionCierre` | caja | Por forma de pago: esperado, contado y diferencia. |
| `Gasto` / `CategoriaGasto` / `AdjuntoGasto` / `BoletaGasto` | caja | Gasto referencial (registrado → confirmado / anulado), categorías, comprobantes adjuntos (archivos privados) y boleta interna numerada. |
| `CredencialIntegracion` / `RegistroSolicitudIntegracion` | integraciones | Credencial de otro sistema (identificador visible, hash de la clave, permisos de consulta, límite por minuto, vencimiento, revocación) y registro de cada solicitud. |
| `ProveedorFacturacion` / `SolicitudElectronica` / `RegistroIntegracion` | facturacion | Proveedor de factura electrónica (credenciales cifradas), solicitud con `id_solicitud` único (idempotencia) y estados, y registro de cada paso de la integración. |
| `Recorrido` | recorridos | `Code`, nombre, período (AAAA-MM, no cambia), estado (planificado → abierto ⇄ cerrado; planificado → anulado), fechas. |
| `AsignacionRecorrido` | recorridos | Cobrador del recorrido (activa o retirada) con fecha y hora de inicio y fin. |
| `ConexionRecorrido` | recorridos | Conexión del recorrido con su orden de visita. Única por conexión y período (restricción de base). |
| `Lectura` | lecturas | Comprobante (L-XXXXXXXX), `id_operacion` del teléfono (única), recorrido, conexión, **instalación** y medidor, período, lectura y fecha anterior (instantánea), lectura actual, consumo (lo calcula el servidor), GPS y distancia a la conexión, origen de la foto, estado (confirmada / requiere revisión / anulada) y resolución. Una confirmada por instalación y período (restricción de base). |
| `FotoLectura` | lecturas | Fotos privadas de la lectura; la principal (medidor) es obligatoria. |
| `Tarifa` | tarifas | Tipo de conexión (`Code`, nombre); una «por defecto» por institución. La conexión apunta a su tarifa (vacío = por defecto). |
| `VersionTarifa` | tarifas | Vigencia desde un período; no se modifica una vez usada. |
| `ConceptoTarifa` | tarifas | Regla: mínimo, excedente, tramo, por m³, fijo o porcentaje; precio sin IVA; IVA 10/5/exento. |
| `Liquidacion` / `LineaLiquidacion` | tarifas | Importe de una lectura confirmada: número LQ-XXXXXXXX, tarifa y versión, instantánea de conceptos, líneas, subtotales por IVA, total. Una vigente por lectura; se anula (no se borra). |
| `CuentaAbonado` / `SesionPortal` | portal | Cuenta de una PERSONA para el portal (global, por documento normalizado): correo verificado contra el padrón, contraseña, PIN temporal (hash, vence, un uso), intentos y bloqueo. Sesiones propias del portal. |
| `MigracionBaseDatos`, `Respaldo`, `ManualPlataforma` | infraestructura | Modelos «sin tabla» que solo generan su entrada en el menú del admin. |

## Patrones importantes

- **Claves (convención del proyecto, `comun/codigos.py`)**: el autonumérico interno (`id`) y los numeradores
  internos **nunca** se muestran ni se aceptan desde la interfaz. Los maestros y cabeceras (clientes, conexiones,
  medidores, zonas, barrios, puntos, rangos, futuros artículos…) llevan **`Code`**: texto, único por institución,
  cargado siempre por el usuario, en mayúsculas, sin cambio después del alta. La API los busca por `Code` en la ruta
  (`VistaPorCode`), los referencia por `Code` (`ReferenciaPorCode`) y la auditoría los registra por `Code`. Los
  documentos de formulario continuo (facturas, notas de crédito) llevan **`SerNr`**, que entrega
  `apps.facturacion.servicios.tomar_sernr(punto, tipo)` desde los rangos del punto de expedición, dentro de la
  misma transacción que guarda el documento.

- **Aislamiento entre instituciones (base central)**: la institución sale solo del token
  (`apps/identidad/autenticacion.py`). Las vistas heredan `comun.vistas.VistaInstitucional` y definen `modelo`;
  la consulta ya llega filtrada y un id ajeno responde 404. Los modelos nuevos heredan
  `comun.modelos.ModeloInstitucional` (FK `PROTECT`, `creado_en`, `actualizado_en`, `objects.de(institucion)`).
  Antes de relacionar registros: `validar_misma_institucion(institucion, *objetos)`.
- **Reglas de negocio en `servicios.py`**: las vistas validan, llaman al servicio y serializan. Errores de regla:
  `comun.errores.ErrorNegocio` → 400 con `{detalle, codigo}`.
- **Permisos en el servidor**: `RequierePermiso` + `permiso_requerido = 'modulo.accion'` (cerrado por defecto
  si la vista no declara permiso). La interfaz solo oculta opciones.
- **Nada se borra**: usuarios y roles se desactivan; instituciones se suspenden o archivan con motivo; la auditoría
  no se puede modificar.
- **Patrón «sin tabla»** para paneles del admin: modelo `managed = False` + `changelist_view` con plantilla propia
  + `get_urls()` para acciones. Ojo: `dumpdata` no los saltea solo (ver D13).
- **`crypto.randomUUID()`** no existe en HTTP plano fuera de localhost: `frontend/src/utilidades/identificador.ts`
  tiene el generador de respaldo. Usarlo siempre (lo necesitará la PWA para los ids de operación).
- **URL de la API** armada desde el host de la página (`frontend/src/api/configuracion.ts`): se prueba desde el
  celular sin editar IPs. `VITE_API_URL` o `VITE_API_MISMO_ORIGEN` solo cuando se necesitan.
- **Archivos privados** (`comun/archivos_privados.py`): fotos y comprobantes en `DIR_PRIVADO` (fuera de `media/`),
  nombre aleatorio, tipo verificado por su contenido, entregados solo por endpoints con permiso. El frontend los
  pide con el token y los muestra desde memoria (`FotoPrivada`); las fotos se achican en el navegador antes de subir.
- **Geografía sin PostGIS** (`comun/geo.py`): coordenadas decimales y polígonos GeoJSON validados; punto dentro de
  polígono en Python. GeoJSON usa [longitud, latitud] y Leaflet [latitud, longitud]: convertir solo con
  `frontend/src/mapa/leaflet.ts`.
- **Aplicación del cobrador (PWA, `frontend/src/cobrador/`)**: ruta `/cobrador`. Descarga el «paquete» del recorrido
  (conexiones, titulares, lecturas anteriores) y lo guarda en IndexedDB (`almacenLocal.ts`). Cada lectura se guarda
  primero en el teléfono con sus fotos y un `id_operacion` (UUID) y después se envía (`sincronizacion.ts`): reenviar
  nunca duplica; recién con la confirmación del servidor se marca enviada y se borran las fotos del teléfono. Todo
  queda asociado al usuario (en un teléfono compartido nadie ve ni envía lo ajeno). La sesión del cobrador se recuerda
  en el teléfono (vence a las 12 h) para abrir sin conexión. `public/sw.js` guarda solo la aplicación (no la API);
  funciona con https.
- **Lecturas: el servidor es la fuente oficial** (`apps/lecturas/servicios.py`): recalcula la lectura anterior (la
  última confirmada de la misma instalación, o la inicial) y el consumo. Lo dudoso no se rechaza ni se pisa: queda
  «Requiere revisión» y se autoriza, corrige o anula con motivo.
- **Cálculo tarifario puro** (`apps/tarifas/calculo.py`): `calcular(conceptos, consumo)` no toca la base; lo usan el
  simulador y las liquidaciones. Cada liquidación guarda los conceptos usados y se puede reproducir exactamente.
- **Manual**: cada módulo nuevo suma su sección en `frontend/src/paginas/Manual.tsx` (usuarios) y, si toca la
  plataforma, en `backend/apps/manual/templates/admin/manual/manual.html`, en el mismo trabajo.

## Pruebas

```bash
cd backend && venv/bin/python manage.py test        # Windows: venv\Scripts\python manage.py test
cd frontend && npm run tipos
```

Incluyen la prueba de aceptación de la Fase 1 (`comun/pruebas/test_aislamiento.py`: dos instituciones no ven
ni modifican datos de la otra aunque conozcan los ids), ingreso y bloqueo, permisos, auditoría inmutable,
backup (contenido y exclusiones), restauración y copia entre bases. Fase 2 (`apps/padron/tests/`): aislamiento del
padrón y del mapa, historial de medidores tras una sustitución, archivados visibles, sin borrado físico, fotos
privadas inaccesibles para otras instituciones o sin permiso, transiciones de estado y filtros; ninguna respuesta
expone el id interno y el `Code` es obligatorio e inmutable. Numeración (`apps/facturacion/tests/`): varios puntos con
series propias, paso al próximo rango, vigencias y timbrados, rangos superpuestos rechazados, rango usado solo ampliable,
número no consumido si el documento no se guarda, contador interno nunca expuesto. Fase 3
(`apps/lecturas/tests/`): el cobrador no lee fuera de su asignación, sin foto o sin GPS no hay lectura, reenvíos
sin duplicados, duplicadas y lecturas menores a revisión, la lectura conserva el medidor tras una sustitución, el
consumo lo calcula el servidor, revisión (autorizar, corregir, anular), fotos privadas y comprobante, y el criterio de
aceptación: un cobrador completa su recorrido y sincroniza (con reintentos) sin duplicar. Fase 5
(`apps/facturacion/tests/test_facturas.py`): varias liquidaciones en una factura, ninguna facturada dos veces,
contado y crédito con vencimiento, IVA repartido sin diferencias de redondeo, anulación que libera, otra institución
no factura lo ajeno, sin modalidad o sin proveedor no se emite, y en la electrónica: un corte deja «estado
desconocido» y no se reenvía a ciegas, el reintento usa el mismo identificador y un rechazo libera las liquidaciones.
Fase 6 (`apps/cobranzas/tests/`): la contado queda pagada con su forma de pago, una factura recibe varios pagos
parciales, un pago se reparte entre varias facturas, no se aplica más que el saldo ni distinto del importe, un
reintento con la misma clave no duplica, reparto manual o automático, anular un recibo revierte el pago y conserva el
original, una factura con recibos no se anula, permisos y aislamiento entre instituciones. Fase 7
(`apps/caja/tests/`): sin caja abierta no se cobra, cada cobro entra una vez y los medios de pago no se suman, una
sesión por cajero y por caja, cierre con y sin diferencias, una sesión cerrada no se altera, la reversión posterior
va a la caja abierta y conserva el original, un gasto confirmado genera un único egreso, boleta interna y adjuntos
privados, permisos y aislamiento. Fase 8 (`apps/informes/tests/`): todos los informes responden con su
definición, lo facturado no se confunde con lo cobrado (los revertidos no cuentan), saldos y antigüedad, exportación a
Excel con números reales y a CSV, permisos por informe, aislamiento entre instituciones, panel; credenciales de solo
lectura con sus permisos, clave mostrada una vez, revocación, vencimiento, límite por minuto y registro. Portal
(`apps/portal/tests/`): el PIN solo se envía al correo del padrón, se usa una vez y obliga a elegir contraseña,
bloqueo por intentos, la persona ve lo suyo en todas las instituciones con portal y nada ajeno, salir y cambio de
contraseña cierran sesiones. Número del medidor: alfanumérico, único, buscable e identificable por el cobrador.

## Variables de entorno (`backend/.env`)

Ver `backend/.env.example`. Las principales: `DEBUG`, `SECRET_KEY` (obligatoria con `DEBUG=False`),
`CLAVE_CIFRADO`, `MODO`, `PUERTO_API`, `PUERTO_WEB`, `ALLOWED_HOSTS` / `CORS_ALLOWED_ORIGINS` /
`CSRF_TRUSTED_ORIGINS` (solo con `DEBUG=False`), `DB_MOTOR` y `DB_*`, `ADMIN_PLATAFORMA_*`,
`RESPALDOS_A_CONSERVAR`, `DIR_RESPALDOS_COPIA`, `VIGENCIA_TOKEN_HORAS`, `INTENTOS_INGRESO_MAXIMOS`,
`MINUTOS_BLOQUEO_INGRESO`, `LIMITE_INGRESO`.

## Limitaciones conocidas

- Las rutas de la API de usuarios y roles todavía usan su id interno (no se muestra en pantalla); su clave visible
  es el nombre de usuario (inmutable) y el `Code` del rol.
- La recuperación de contraseña por correo necesita el correo cargado en el usuario y un servidor de correo (sin
  él, los correos quedan como archivos en `backend/datos/correos/`); si no, la restablece un administrador.
- El frontend no tiene pruebas automáticas propias: se probó el flujo completo del cobrador (con corte de conexión)
  y de la oficina con un navegador automatizado en el entorno de desarrollo.
- Lecturas: no se cargan lecturas desde la oficina (la foto y el GPS son obligatorios). El escaneo del medidor con la cámara (código
  de barras/QR) no está: se escribe el número.
- La aplicación del cobrador se instala y abre sin conexión solo con https (servidor). En la red local por http
  funciona, pero sin GPS ni instalación (límite de los navegadores).
- Mapa: «morosa» solo considera facturas a crédito vencidas; el consumo sin facturar no vence mientras no se
  definan las reglas de vencimientos, mora, recargos y suspensión (D50). Los mapas usan los mosaicos públicos de
  OpenStreetMap (requieren internet).
- El GPS del navegador solo funciona con HTTPS (o en la misma PC): en la red local sin HTTPS se marca en el mapa.
- La migración a PostgreSQL se probó con el mismo mecanismo entre dos SQLite; la prueba contra un PostgreSQL
  real se hace en el servidor.
