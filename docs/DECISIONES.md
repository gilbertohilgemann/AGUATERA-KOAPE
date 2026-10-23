# Decisiones técnicas — Koape Aguateras

Registro de por qué se eligió cada solución importante (sección 23 de `informacion-tecnica.txt`).
Formato: decisión · motivo · consecuencias.

---

## Decisiones de arquitectura confirmadas (20/10/2026)

### D1 · SQLite en desarrollo, PostgreSQL en producción
- **Decisión**: desarrollo en SQLite (cero configuración); producción en PostgreSQL. Las coordenadas y polígonos de la Fase 2 se guardarán como GeoJSON (campos JSON) y las consultas geográficas pesadas se activarán con PostGIS en producción.
- **Motivo**: lo pide la convención («SQLite por defecto») y evita instalar PostGIS en cada PC de desarrollo.
- **Consecuencias**: el módulo «Migración de base de datos» pasa los datos de un motor a otro sin perderlos. El instalador del servidor (`scripts/servidor/instalar_fedora.sh`) deja PostgreSQL configurado desde el inicio.

### D2 · Una base central compartida
- **Decisión**: una sola base; cada registro de negocio lleva su `institucion` (FK `PROTECT`), con unicidades compuestas `(institucion, código)`.
- **Motivo**: lo pide la especificación (sección 4) y simplifica los indicadores de plataforma.
- **Cómo se garantiza el aislamiento** (ver «Patrones importantes» en el README):
  1. La institución de cada solicitud sale **solo del token** (`AutenticacionToken`), nunca de un parámetro del navegador.
  2. Las vistas usan `VistaInstitucional`: la consulta ya viene filtrada; un id de otra institución responde 404.
  3. Los serializadores arman sus listas de opciones (roles, etc.) filtradas por institución: un id ajeno responde «no existe».
  4. `validar_misma_institucion()` en los servicios y una señal `m2m_changed` que impide, aunque una vista falle, asignar un rol de otra institución.
  5. Restricciones de base: un usuario de institución no puede ser personal de la plataforma (`CheckConstraint`).
- **Prueba de aceptación**: `comun/pruebas/test_aislamiento.py`.

### D3 · Reutilizar Koape Hotel-Restaurante
- **Decisión**: se tomaron del Hotel-Restaurante (probado en producción) y se adaptaron a una base central: identidad (tokens con hash, bloqueo por intentos, honeypot, igualación de tiempos), permisos granulares por rol, auditoría, cifrado de secretos, migración de base, backup y restauración, chequeo de seguridad, scripts de instalación/arranque (Linux, Windows y servidor Fedora) y la base del frontend (estilos de marca, cliente de API, sesión).
- **Diferencias con el Hotel**: no hay base maestra ni una base por empresa; el usuario es un modelo propio (ver D5); el ingreso no lleva la empresa en la ruta sino solo el código institucional.

### D4 · Despliegue
- **Decisión**: VPS Fedora Cloud, dominio `aguateras.koapesystem.com` (todavía no creado), convive con otros proyectos (se agrega un sitio al servidor web existente sin tocar los demás).
- **Consecuencias**: `scripts/servidor/instalar_fedora.sh` usa ese dominio por defecto; el certificado HTTPS se obtiene cuando el DNS apunte al servidor (`scripts/servidor/https.sh`).

---

## Decisiones técnicas de la Fase 1

### D5 · Modelo de usuario propio (`identidad.Usuario`)
- **Motivo**: con una base central, el mismo nombre de usuario («admin») debe poder existir en varias instituciones. El `auth.User` de Django exige `username` único global.
- **Cómo**: `institucion` (vacía = usuario de la plataforma) + `nombre_usuario`; el campo con el que Django identifica (`identificador`, único) se arma solo: `usuario` para la plataforma y `CODIGO/usuario` para una institución. Por eso el **código institucional no se puede cambiar** después del alta.

### D6 · Autenticación por token propio (no sesión de Django)
- **Motivo**: la PWA del cobrador (Fase 3) trabaja sin conexión y se sincroniza; un token en cabecera es más simple y seguro que cookies cruzadas entre puertos/dominios.
- **Cómo**: token aleatorio de 256 bits; en la base solo su hash SHA-256; vence a las 12 h (`VIGENCIA_TOKEN_HORAS`); se revoca al salir, al cambiar la contraseña, al desactivar al usuario y al suspender la institución. El frontend lo guarda en `sessionStorage` (se borra al cerrar la pestaña). Se revisará en la Fase 3 la duración de la sesión del cobrador sin conexión.

### D7 · Recuperación de contraseña sin correo (por ahora) — reemplazada por D51
- **Decisión**: un administrador institucional restablece la contraseña (el usuario debe cambiarla al ingresar y se cierran sus sesiones). Si la institución perdió a su administrador, lo hace el superusuario de la plataforma desde el panel. Todo queda auditado.
- **Motivo**: la recuperación por correo necesita un servidor de correo configurado (decisión pendiente). Se agrega cuando haya SMTP.

### D8 · Contraseña inicial obligatoria de cambiar
- Usuario nuevo o contraseña restablecida → `debe_cambiar_contrasena`. El servidor rechaza cualquier endpoint de negocio hasta cambiarla (no solo la interfaz).

### D9 · Auditoría de solo inserción
- `RegistroAuditoria` rechaza `save()` sobre registros existentes, `delete()` y `update()/delete()` masivos; el admin es de solo lectura. Guarda antes/después, IP e id de solicitud (`X-Id-Solicitud`, generado por el frontend con respaldo si no hay `crypto.randomUUID`). Las claves sensibles (contraseñas, tokens, secretos) se descartan antes de guardar.

### D10 · Modalidad de facturación fuera del alcance de la institución
- La institución no puede cambiar su modalidad de facturación (ni su código o estado): la define la plataforma según las habilitaciones fiscales. Mientras sea «No configurada», el sistema no emitirá facturas (Fase 5).

### D11 · Sin Redis/Celery en la Fase 1
- No hay tareas en segundo plano todavía. El respaldo diario corre con un timer de systemd (servidor) o una tarea programada (Windows/cron). Se reevalúa en la Fase 5 (facturación electrónica con reintentos).

### D12 · Puertos: web 5206 · API 9006
- Pedido del cliente (21/10/2026; antes eran 5215 / 8015). Distintos de los del Hotel-Restaurante (5205 / 8005) para
  que ambos sistemas convivan en la misma PC. Si están ocupados por otra cosa, los scripts no la tocan: buscan el
  siguiente libre y avisan.

### D13 · El volcado de la migración excluye los modelos «sin tabla»
- `dumpdata` no saltea solo los modelos `managed = False` (paneles del admin) e intenta leer una tabla inexistente. Se excluyen dinámicamente (`db_migracion._excluidos`). Lo detectó la prueba `apps/migracion_bd/tests/test_copia.py`.

### D14 · Sin escalada de privilegios entre roles (revisión de seguridad)
- Quien no es administrador institucional solo otorga permisos que él tiene (al editar roles), solo asigna roles cuyos permisos tiene, no cambia sus propios roles y solo gestiona (edita, desactiva, restablece la contraseña) a usuarios con permisos que él tiene (`serializadores.puede_gestionar`).
- Otros ajustes de la misma revisión: la auditoría siempre hace INSERT (`force_insert`), el límite de ingreso y la IP de auditoría usan la IP real detrás del proxy (`NUM_PROXIES=1` en el servidor), límite de 10 cambios de contraseña por hora, nombres de usuario validados, zona horaria validada, restauración PostgreSQL en una sola transacción y abortada si no se pudo respaldar lo actual, manifiesto dañado informado sin romper. Pruebas: `apps/identidad/tests/test_revision.py`.

---

## Fase 2 · Padrón y mapa (20/10/2026)

### D15 · Reglas del padrón confirmadas
- Un cliente puede tener **varias conexiones**.
- Una conexión tiene **un medidor vigente**: restricción de base `UNIQUE(conexion) WHERE fecha_retiro IS NULL` (y lo mismo por medidor). La sustitución retira e instala en una sola transacción; la instalación vieja conserva medidor, fechas y lecturas.
- Cada **barrio pertenece a una zona**; la zona de la conexión sale de su barrio.

### D16 · Estados de la conexión y transiciones
`en_instalacion → activa | pendiente_ubicacion | archivada` · `pendiente_ubicacion → activa (exige coordenadas) | en_instalacion | archivada` · `activa → suspendida | desconectada | pendiente_ubicacion` · `suspendida → activa | desconectada` · `desconectada → activa | archivada` · `archivada → desconectada` (restauración). Todo cambio pide motivo y queda auditado. El estado y el titular no se cambian por la edición común: tienen su propio procedimiento.

### D17 · ~~Códigos automáticos por institución~~ (reemplazada por D23)
Se generaban `C-000001` / `CX-000001` con la tabla `Secuencia`. Desde la convención de claves (D23) el código lo carga siempre el usuario.

### D18 · Geografía en GeoJSON, sin PostGIS por ahora
Coordenadas en decimales (6 decimales ≈ 11 cm) validadas dentro de Paraguay (detecta latitud y longitud invertidas). Polígonos `Polygon`/`MultiPolygon` validados (anillos cerrados). El filtro por zona usa la relación barrio→zona, no la geometría. Con PostGIS en producción se podrán pasar a consultas espaciales sin cambiar la API.

### D19 · Fotos privadas
`DIR_PRIVADO` fuera de `media/`; tipo verificado por la firma del archivo (JPG, PNG, WEBP), máximo 8 MB, nombre aleatorio por institución. Al reemplazar una foto la anterior no se borra (queda referenciada en la auditoría). El frontend achica la foto (1600 px, JPEG 80 %) antes de subirla, preparando la PWA.

### D20 · Lectura de retiro menor que la inicial
No se rechaza siempre (el contador puede volver a cero): se exige confirmarla explícitamente con un motivo. La regla de cálculo del consumo en esos casos se define en la Fase 3/4.

### D21 · Mapa con Leaflet + OpenStreetMap, sin plugins
Puntos como `circleMarker` (no dependen de íconos), polígonos dibujados con un editor propio (clic por vértice), popups armados con nodos de texto (sin HTML con datos: evita inyección). Los mosaicos de OpenStreetMap requieren internet y respetar su política de uso; si el volumen crece se puede cambiar el proveedor en `frontend/src/mapa/leaflet.ts`.

### D22 · Ajustes de la revisión independiente de la Fase 2
- Una conexión no puede recibir un medidor con fecha anterior a su último retiro (los períodos no se superponen).
- Una conexión **activa** necesita ubicación siempre (si no se conoce, «Pendiente de ubicación»); para archivarla hay que retirar antes el medidor; no se restaura con el titular archivado; el cambio de titular no admite fechas futuras.
- Los nombres de zonas y barrios en los tooltips del mapa se insertan como texto (evita inyectar código).
- Parámetros de filtro inválidos (ej. `?zona=abc`) devuelven una lista vacía en vez de un error 500.
Pruebas: `RevisionPadronTests` en `apps/padron/tests/test_padron.py`.

---

## Convención de claves `Code` / `SerNr` (20/10/2026)

### D23 · `Code` en maestros, autonumérico solo interno
- **Decisión** (pedido del cliente): «el contador autonumérico es interno, no debe estar accesible al usuario». Los
  registros maestros o de cabecera llevan un campo de texto **`Code`** (nombre literal, como en OpenOrange y el
  Hotel-Restaurante: única excepción a «todo en castellano»), único por institución y **cargado siempre por el
  usuario** (el sistema no lo sugiere).
- **Cómo**: `comun/codigos.py` (`campo_code`, `CodeSerializerField`, `ReferenciaPorCode`, `VistaPorCode`). Se guarda
  en mayúsculas, admite letras, números, `.`, `-` y `_` (máx. 40) y no se cambia después del alta. Aplica a Zona,
  Barrio, Cliente, Conexion, Medidor (su número de serie pasa a ser su `Code`), PuntoExpedicion y RangoNumeracion; los
  módulos nuevos con maestros (artículos, conceptos, tarifas…) lo usan desde el inicio.
- **Consecuencias**: la API busca y referencia por `Code` (rutas, cuerpos, filtros, mapa); ninguna respuesta del
  padrón ni de la numeración incluye `id`; la auditoría registra `Code` (y nombre de usuario, nombre de rol o código
  institucional en lugar de ids). La tabla `Secuencia` queda solo para numeradores internos. Como todavía no había
  datos reales, las migraciones iniciales de `territorio` y `padron` se regeneraron.
- **Roles y usuarios**: el rol también tiene `Code` (los iniciales: `COBRADOR`, `CONSULTA`; migración
  `identidad/0002` lo completa desde el nombre) y el nombre de usuario pasa a ser inmutable: son las claves que
  registra la auditoría. Sus pantallas no muestran el id, aunque la API de usuarios y roles todavía lo usa para las
  rutas (pendiente menor, sin impacto visible).

### D24 · `SerNr` por rangos de cada punto de expedición
- **Decisión**: los documentos de formulario continuo —**facturas y notas de crédito**— llevan `SerNr`, tomado de los
  rangos «desde–hasta» que la institución configura **por punto de expedición y tipo de documento**. Una institución
  puede tener dos o más puntos (001-001, 001-002…).
- **Cómo** (`apps/facturacion`): `PuntoExpedicion`, `RangoNumeracion` (timbrado, vigencia, `ultimo_usado` interno) y
  `tomar_sernr(punto, tipo, fecha)`: bloquea el punto y sus rangos, usa el rango activo y vigente en orden y pasa
  al siguiente cuando se agota; sin numeración disponible no se emite (`sin_numeracion`). Debe ejecutarse en la misma
  transacción que guarda el documento: si falla, el número no se consume (no quedan huecos).
- **Unicidad**: `SerNr` es único por institución + punto + timbrado en cada tipo de documento (`DocumentoNumerado`,
  base de la Fase 5); con un timbrado nuevo la numeración puede volver a empezar en 1. Los rangos del mismo punto,
  tipo y timbrado no se superponen. Un rango usado solo admite ampliar «hasta», cambiar vigencia u observaciones o
  desactivarse; un punto que ya emitió no cambia su establecimiento ni su número.
- **La numeración nunca retrocede** (revisión independiente): un rango nuevo o ampliado debe continuar después del
  mayor número ya emitido con el mismo punto, tipo y timbrado; y en una misma fecha un punto usa un solo timbrado por
  tipo de documento (dos rangos activos de timbrados distintos no pueden tener vigencias que se crucen). Los rangos
  sin fecha de inicio se usan primero igual en SQLite y PostgreSQL. Todas las escrituras bloquean primero el punto y
  después sus rangos (sin bloqueos cruzados). `tomar_sernr` exige la institución de la sesión.
- Pruebas: `apps/facturacion/tests/test_numeracion.py`.

---

## Fase 3 · Recorridos y lecturas (20/10/2026)

### D25 · Reglas confirmadas
- Lecturas **mensuales** (período AAAA-MM). **GPS obligatorio**: sin ubicación no se confirma la lectura (en el
  teléfono ni en el servidor). Foto del medidor **obligatoria**; la de galería solo si la institución la habilita
  (`Institución → Lecturas`), y la lectura queda marcada. En la v1 el **cobrador solo toma lecturas** (no cobra).
- Una conexión está en **un solo recorrido por período** (restricción de base): dos cobradores no leen la misma.

### D26 · El servidor es la fuente oficial
Al recibir cada lectura el servidor recalcula la lectura anterior (la última **confirmada** de la misma instalación en
un período anterior; si no hay, la lectura inicial de la instalación) y el consumo; lo que mostró el teléfono sin
conexión es solo una estimación. La lectura guarda la instalación y el medidor de ese momento (prueba obligatoria 5)
y una instantánea de lo usado. No se recalcula sola si después cambia algo.

### D27 · Lo dudoso va a revisión, no se rechaza ni se pisa
Quedan «Requiere revisión», sin consumo: lectura menor que la anterior (vuelta a cero, cambio de medidor no
registrado…: el sistema no calcula consumos negativos; quien autoriza indica el consumo), otra lectura del mismo
período (una sola confirmada por instalación y período, restricción de base), ya hay una lectura de un período
posterior, y lo que pudo cambiar mientras el teléfono estaba sin conexión: medidor sustituido o movido (la lectura
queda en la conexión donde estaba el medidor al leer), recorrido cerrado, asignación retirada, conexión quitada del
recorrido (el cobrador no ve los datos del titular en ese caso), foto de galería sin estar habilitada, reloj del
teléfono adelantado. Se rechazan (no se guardan) solo los casos de seguridad o datos inválidos: cobrador nunca
asignado, recorrido no abierto, medidor inexistente o de otra institución, sin foto, sin GPS.
Al autorizar o corregir se recalcula la lectura anterior. No se autoriza si ya hay una lectura confirmada de un
período posterior, ni se corrige o anula si hay lecturas posteriores vigentes (cambiaría sus consumos): se
resuelven en orden. (Ajustes de la revisión independiente de la Fase 3.)

### D28 · Sincronización sin duplicados
El teléfono genera un `id_operacion` (UUID) por lectura; el servidor lo guarda con unicidad: un reintento devuelve
la misma lectura (200 `ya_recibida`). La lectura y sus fotos se guardan juntas (todo o nada). El teléfono marca
«enviada» y borra las fotos recién con la confirmación del servidor. Un rechazo por regla queda como «Rechazada» con
el mensaje (reintentar o descartar); sin conexión o error del servidor queda pendiente con todo intacto.

### D29 · Datos en el teléfono
- Antes de la foto la aplicación muestra solo orden de visita, dirección y barrio; titular, medidor, lectura
  anterior y foto de la vivienda se ven después de fotografiar el medidor (paso 2 de la especificación). Los datos
  vienen en el paquete descargado (necesario sin conexión): la aplicación los oculta hasta la foto.
- Todo queda asociado al usuario; los paquetes se borran al finalizar el recorrido (si no hay pendientes) o al salir,
  y a los 45 días; las lecturas enviadas (ya sin fotos) a los 7 días.
- La sesión del cobrador se recuerda en el teléfono (localStorage) hasta que vence (12 h) o se sale, para abrir la
  aplicación sin conexión; en el panel de oficina sigue siendo solo de la pestaña (D6).

### D30b · Ajustes de la revisión independiente (aplicación)
- Ingresar descarta la sesión recordada de otra persona en el mismo teléfono; la copia de la sesión está atada al
  token. El cliente de la API se crea una sola vez (antes se recreaba en cada navegación).
- Una lectura que el servidor rechaza con error 5xx no traba la cola: se sigue con las demás.
- Se pide al navegador almacenamiento persistente; el service worker solo guarda páginas correctas (no errores ni
  portales wifi). Un medidor que no figura en el paquete descargado se puede leer igual (queda para revisión).

### D30 · PWA sin dependencias nuevas
Manifiesto y service worker propios (`frontend/public/`), sin plugins: el service worker guarda solo la aplicación,
nunca respuestas de la API ni fotos. Requiere https (lo exige el navegador, igual que el GPS). Comprobante PDF con
ReportLab (nueva dependencia del backend), tamaño A6, con la foto principal; dice que no es factura ni recibo.

---

## Fase 4 · Tarifas y liquidaciones (21/10/2026)

### D31 · Estructura tarifaria confirmada
Configurable por institución y por **tipo de conexión** (una tarifa por tipo; las conexiones sin tipo usan la
tarifa «por defecto»). Conceptos: **consumo mínimo** (m³ del mínimo × precio, se cobra se use o no), **excedente**
(precio fijo por m³ por encima del mínimo), y además tramos escalonados, precio por m³, cargo fijo y
**porcentajes** como la **tasa ERSSAN**. Precios sin IVA; el IVA se calcula aparte por tasa.

### D32 · ERSSAN e IVA (investigado el 21/10/2026)
- **ERSSAN** (Ley 1614/2000, art. 22): tasa retributiva que fija el ERSSAN cada año, de hasta el **2 % de cada
  facturación**, calculada sobre el importe del servicio **excluidos impuestos, tasas y contribuciones**; la paga el
  usuario, la cobra el prestador y va discriminada en la factura. Se configura como concepto «porcentaje» (exento)
  sobre la suma de los demás conceptos.
- **IVA**: configurable por concepto (10 %, 5 % o exento). La DNIT dictaminó (consultas vinculantes de 12/2025 y
  N° 876/2026) que el servicio de agua de juntas de saneamiento **sin fines de lucro** está **exonerado de IVA**
  (Ley 6380/2019, art. 100 num. 5) y deben facturar como exentas; una aguatera con fines de lucro grava el servicio.
  Por eso no se fija una tasa en el sistema: cada institución la configura según su situación (con su contador).
- Guaraníes: cada línea se redondea a entero (mitad hacia arriba) y el IVA por tasa sobre el subtotal gravado.

### D33 · Liquidación automática y reproducible
La liquidación se genera en la misma transacción en que la lectura queda confirmada (al recibirla, autorizarla o
corregirla). Usa la tarifa de la conexión y la versión vigente en el período de la lectura, y guarda la instantánea
de los conceptos, las líneas y los totales; `calcular()` es una función pura, así la liquidación se reproduce
exactamente. Una versión usada no se modifica (se crea otra). Corregir o anular la lectura anula la liquidación
(queda en el historial) y, si sigue confirmada, se calcula otra. Sin tarifa vigente la lectura igual se confirma y
queda «sin liquidar» hasta «Liquidar pendientes». En la Fase 5 una liquidación facturada ya no se anula así.

### D34 · Ajustes de la revisión independiente de la Fase 4
- **Sin precios retroactivos**: una versión nueva (o un cambio a una sin usar) no puede empezar en un período que ya
  tiene liquidaciones con esa tarifa. La versión se bloquea mientras se liquida (nadie cambia sus conceptos a la vez).
- **Un solo cálculo del consumo** por versión: mínimo + excedente, tramos (desde 0 o desde donde termina el mínimo,
  contiguos y el último sin límite) o precio por m³; no combinados (cobrarían dos veces los mismos m³).
- Al corregir una lectura se reliquida con la tarifa de su liquidación anterior (la del período), aunque la conexión
  haya cambiado de tipo después. «Liquidar pendientes» usa la tarifa actual de la conexión.
- Columnas de importes ampliadas (un consumo desmesurado ya no da error); importes por encima de 10^15 no se liquidan.
- La tarifa por defecto siempre activa y única (cambios serializados por institución).
- En pantalla los números se escriben como en Paraguay (punto de miles, coma decimal): «2.500» son dos mil quinientos.
- Simular no guarda nada: lo puede usar quien consulta liquidaciones; el resumen lo ve quien gestiona tarifas.

---

## Fase 5 · Facturación (21/10/2026)

### D35 · Factura electrónica: capa desacoplada, sin proveedor inventado
- La especificación prohíbe inventar URLs, endpoints o formatos. `apps/facturacion/electronica.py` define la interfaz
  `Adaptador` (enviar, consultar) y un registro de adaptadores **vacío**: cuando la institución elija su proveedor y
  entregue su documentación se programa el adaptador. Mientras tanto una institución en modalidad electrónica no
  puede emitir (`proveedor_no_configurado`).
- Flujo seguro: la solicitud se guarda (con `id_solicitud` único) antes de llamar al proveedor; un corte deja
  «estado desconocido» y se **consulta**, nunca se reenvía a ciegas; los reintentos usan el mismo identificador; cada
  paso queda en `RegistroIntegracion` sin credenciales; un rechazo libera las liquidaciones.

### D36 · Factura autoimpresa en PDF
- A4 con emisor y RUC, timbrado y vigencia, número 001-001-0000001, fecha, condición y vencimiento, cliente, líneas
  con columnas exentas / 5 % / 10 % (IVA incluido), liquidación del IVA y total. Son los datos de uso general
  (Decreto 6539 art. 19 y la reglamentación de la DNIT): **cada institución debe validarlo con su contador** y su
  autorización de autoimpresor antes del uso fiscal.
- Se anula (con motivo), no se borra: el número queda usado y el PDF sale con la marca «ANULADA».

### D37 · Cuándo y cómo se factura (respuesta del cliente)
- La factura se genera **cuando el usuario viene a pagar** (caja), no al liquidar.
- Una factura puede llevar **varias liquidaciones** del mismo cliente; cada liquidación va **entera** a una sola
  factura vigente (restricción de base).
- Pago en partes: se emite la factura **a crédito**; los pagos parciales se aplican a ella (Fase 6).
- Crédito: vence a los `dias_vencimiento_credito` de la institución (30 por defecto, editable en Institución).
- Una liquidación ya facturada no se re-liquida (corregir la lectura exige anular antes la factura).
- El cobrador ve, después de registrar la lectura, lo pendiente de facturar y las facturas a crédito con su saldo y
  atraso (solo informativo; el saldo real descuenta pagos desde la Fase 6).

---

## Fase 6 · Pagos y recibos (21/10/2026)

### D38 · Contado y crédito (respuesta del cliente)
- **Contado**: el pago se registra en el mismo paso que la factura (forma de pago obligatoria; transferencia y POS
  piden la referencia). La factura contado es el comprobante: no lleva recibo.
- **Crédito**: se cobra después con **recibos**, cada uno con su pago aplicado a una o varias facturas; una factura
  puede recibir varios pagos (parciales).
- Anular una factura contado **revierte** su pago (se conserva, con motivo); una factura con recibos vigentes no se
  anula hasta anular esos recibos. Si una factura electrónica contado es rechazada, su pago se revierte.

### D39 · Reparto, número de recibo y excedente (sin preferencia del cliente: se tomó lo recomendado)
- **Reparto** configurable por institución (`aplicacion_pagos`): **manual** por defecto (la especificación pide no
  imponer una política sin confirmación) o **automático** (la vencida más antigua primero; a igual vencimiento, la
  más antigua y de menor número). En los dos casos la pantalla muestra el reparto antes de confirmar.
- **Número de recibo**: correlativo propio de cada institución (0000001…), sin timbrado: el recibo no es documento
  fiscal. Es un número de DOCUMENTO (como el SerNr), no el id interno del registro, que sigue sin exponerse.
- **Sin saldo a favor**: el importe no puede superar la deuda a crédito elegida; la suma aplicada debe ser igual al
  importe. El vuelto se entrega en el momento.

### D40 · Consistencia de los cobros
- El saldo **se deriva** de las aplicaciones vigentes (nunca se guarda «pagada»); el estado de cobro (pagada, parcial,
  pendiente, vencida) también.
- Cobrar y anular bloquean las facturas del cliente (`select_for_update`, en orden fijo) y recalculan los saldos
  dentro de la transacción. Cada cobro lleva una **clave** generada por la pantalla: un reintento con la misma clave
  devuelve el mismo recibo; la restricción única en la base cubre dos envíos simultáneos.
- Anular un recibo no borra nada: recibo ANULADO, pago REVERTIDO y aplicaciones REVERTIDAS, con motivo y auditoría.
  El movimiento compensatorio de caja llega con la Fase 7.
- El rol inicial CONSULTA ahora puede consultar facturas y cobros (migración para las instituciones existentes).
- Revisión independiente: la clave se vuelve a buscar DESPUÉS de tomar los bloqueos (un reintento que esperó al
  primero devuelve el mismo recibo, no «sin saldo»); la pantalla conserva la clave si la conexión se corta o el
  servidor falla (solo la renueva ante un rechazo definitivo 4xx); una clave repetida con otro cliente, importe o
  forma de pago se rechaza; los bloqueos no usan DISTINCT (PostgreSQL no lo admite con FOR UPDATE). Las pruebas se
  corrieron también contra PostgreSQL 16.
- Esa corrida en PostgreSQL encontró además: «Liquidar pendientes» (Fase 4) bloqueaba con un JOIN externo
  (PostgreSQL no lo admite); ahora todos los bloqueos con `select_related` usan `select_for_update(of=('self',))`.
  Y la migración de base del panel crea la base PostgreSQL siempre en UTF-8 y rechaza una existente en otra
  codificación (con SQL_ASCII fallan los acentos y la auditoría).

---

## Fase 7 · Caja y gastos (21/10/2026)

### D41 · Respuestas del cliente
- **Caja obligatoria para cobrar**: factura contado y recibos exigen la sesión ABIERTA de quien cobra
  (`caja_cerrada`). Así el cierre siempre cuadra con los cobros.
- **Una sesión por cajero**: cada cajero abre su sesión en una caja libre; un cajero no tiene dos abiertas y una
  caja no está abierta por dos (restricciones de base).
- **Rendición del cobrador**: queda para cuando el cobrador cobre (en la v1 solo toma lecturas, D25).
- **Gastos**: los confirma quien tenga el permiso `gastos.confirmar` (puede ser quien lo registró).

### D42 · Reglas de la caja
- Los movimientos nacen SOLO de cobros, gastos confirmados o sus reversiones (no hay ingresos manuales que dupliquen
  un cobro). Un ingreso por pago y un egreso por gasto, garantizados por la base.
- Saldos separados por forma de pago; el efectivo inicial se cuenta en la primera forma de tipo efectivo.
- Cierre: se declara lo contado de cada forma con movimiento; sin diferencias → cerrada; con diferencias → en
  revisión (observación obligatoria) hasta que un supervisor escriba el resultado.
- Una sesión cerrada no recibe movimientos. La reversión de un cobro o gasto va a la sesión original si sigue
  abierta; si no, a la caja abierta de quien revierte (si no tiene, debe abrirla). Una reversión automática sin
  usuario (rechazo del proveedor electrónico) va a la original y la deja en revisión: visible, nunca silenciosa.
- Cobrar, confirmar gastos y cerrar bloquean la fila de la sesión: un cobro no entra a una caja que se está cerrando.

### D43 · Gastos referenciales
- Registrado no mueve la caja; confirmado genera el egreso (repetir la confirmación no duplica); anulado conserva
  el egreso y agrega el ingreso compensatorio. Un confirmado no se edita.
- Comprobantes adjuntos como archivos privados (foto o PDF). Sin comprobante: boleta interna con número correlativo
  propio (como el recibo, D39), PDF para firmar y foto de la boleta firmada. Con la boleta impresa no cambian los
  datos que figuran en ella.
- Categorías iniciales configurables. No se generan facturas de compra ni asientos contables.

### D44 · Ajustes de la revisión independiente de la Fase 7
- La forma de pago donde se cuenta el saldo inicial se fija al ABRIR la sesión: el arqueo de una sesión vieja no
  cambia si después se reordenan o desactivan formas de pago. Sin forma de tipo efectivo no se abre con saldo.
- Una reversión automática que vuelve a poner en revisión una sesión cerrada queda en la auditoría
  (`caja_reabierta_a_revision`) y borra la marca de «revisada»; las revisiones se acumulan en un historial (nunca se
  pisa la anterior).
- Al cerrar no se puede declarar un importe en una forma sin movimientos (la diferencia no figuraría en el arqueo);
  formato de `declarados` validado y sin formas repetidas. La lista de sesiones muestra la diferencia de CADA forma.
- Dos aperturas simultáneas del mismo cajero responden «ya tiene una caja abierta» (no un error del servidor).
- Los roles existentes que ya facturaban o cobraban reciben `caja.operar` (migración): sin él, después de actualizar
  no podrían abrir la caja ni cobrar.
- Queda permitido que un supervisor revise su propia sesión (coherente con «según permiso», D41); si la institución
  quiere control de dos personas, no le dé `caja.supervisar` al mismo cajero.

---

## Fase 8 · Informes e integración (21/10/2026)

### D45 · Informes con definiciones explícitas
- Cada informe declara QUÉ cuenta (viaja en la respuesta, en la pantalla y en el Excel). Se separa lo FACTURADO
  (facturas vigentes por fecha de emisión) de lo COBRADO (pagos confirmados por fecha del cobro, sin los revertidos);
  los saldos se derivan de las aplicaciones vigentes y el consumo sin facturar se muestra aparte.
- Cada informe exige el permiso de su módulo; el panel del inicio muestra solo las secciones permitidas.
- Exportación a Excel (.xlsx, columnas numéricas reales) y CSV («;», BOM UTF-8), elegido por el cliente. Los textos
  que empiezan con = + - @ se exportan literales (sin fórmulas). Cada exportación queda en la auditoría.
- «Rendiciones pendientes» no aplica en la v1 (el cobrador no cobra, D41).

### D46 · Credenciales de integración (respuestas del cliente)
- Las crea el administrador de cada institución (permiso `integraciones.administrar`); en la v1 son de SOLO LECTURA.
- La credencial actúa como un usuario de consulta con los permisos elegidos: usa las mismas vistas, filtros por
  institución y reglas que la aplicación (sección 16: sin lógica duplicada).
- Clave `kpa_<identificador>_<secreto>`: se muestra una vez y se guarda su hash (SHA-256); revocable, con
  vencimiento opcional, límite por minuto (caché del proceso: con un solo proceso de waitress es exacto; con varios
  procesos sería por proceso) y registro de cada solicitud.
- Las escrituras desde otros sistemas quedan preparadas (servicios de dominio con idempotencia) y se habilitarán
  cuando se defina una integración concreta.

### D47 · Ajustes de la revisión independiente de la Fase 8
- Nadie puede dar a una credencial permisos que él mismo no tiene (`permiso_ajeno`).
- Filtros con caracteres inválidos (ej. NUL, que PostgreSQL rechaza) o un estado desconocido responden 400.
- Panel: cada indicador exige el mismo permiso que el informe que lo detalla; la deuda se suma en la base (sin
  recorrer facturas en Python).
- CSV: los números (también negativos) no llevan apóstrofo y se agrega la fila de totales; en Excel solo un texto
  que empieza con «=» se protege (es lo único que Excel tomaría como fórmula en un archivo .xlsx).
- Las solicitudes con una clave revocada o vencida también quedan en el registro de la credencial; el bloqueo de
  rutas usa la ruta sin el prefijo de publicación.
- Avance de lecturas: solo cuentan las conexiones que siguen en el recorrido (no pasa del 100 %). Saldos y
  antigüedad incluyen las facturas a crédito en trámite con el proveedor electrónico. Con zona o barrio, el informe
  de saldos muestra a los clientes con alguna conexión ahí (con toda su deuda), y así lo dice su definición.
- Pantalla de informes: solo vale la respuesta de la última consulta (cambiar rápido de informe no mezcla datos), se
  exporta exactamente lo que está a la vista y los errores de la exportación se muestran con su mensaje.

## Portal de abonados y mejoras del cobrador (21/10/2026)

### D48 · Una cuenta por persona para todas las instituciones (respuestas del cliente)
- La cuenta del portal es de la **persona** (abonado), no de una institución: se identifica por su número de
  documento normalizado (C.I., RUC, DNI…; sin puntos, espacios ni guiones, y el RUC sin dígito verificador). Con una
  sola cuenta ve sus datos en **todas** las instituciones donde figura como cliente **con ese documento y ese mismo
  correo** y que tienen el portal activo (`Institucion.portal_abonados`, lo decide cada institución; por defecto
  apagado). Exigir también el correo en cada ficha evita que un documento repetido o mal cargado en otra institución
  muestre datos de otra persona. Los documentos de relleno («0», «S/N», «11111»…: menos de 5 dígitos o todos iguales)
  no sirven para el portal.
- **Activación**: documento + correo. Solo se envía el PIN si ese correo está cargado en la ficha de un cliente con
  ese documento (el padrón es la fuente de verdad: la persona no puede registrar un correo nuevo). La respuesta es
  siempre la misma y tarda lo mismo, coincidan o no, también si se pide de nuevo antes de un minuto (no se reenvía)
  o si el servidor de correo falla (con SMTP el correo sale en segundo plano). No revela quién es cliente.
- **Ingreso**: un solo mensaje para todo error (dato incorrecto, cuenta inexistente o bloqueada) y siempre se
  comparan dos hashes: ni el mensaje ni el tiempo revelan qué documentos tienen cuenta. Un correo compartido por
  varias cuentas (familiares) no sirve como usuario: se ingresa con el documento.
- **PIN**: 6 dígitos, se guarda solo su hash, vence a los 15 minutos, sirve una sola vez y hay que esperar 1 minuto
  para pedir otro (además, 10 pedidos por hora por IP). Al ingresar con el PIN, la persona debe elegir su contraseña
  antes de ver nada; al cambiarla se cierran sus demás sesiones. 5 intentos fallidos bloquean la cuenta 15 minutos.
- **Sesión separada del personal**: `Authorization: Portal <token>` solo sirve en `portal/…` y el token del personal
  no sirve en el portal (ni al revés). Sesiones de 8 horas, revocables.
- **Qué ve**: deuda (facturas a crédito con saldo y consumos todavía sin facturar), facturas y recibos (PDF), pagos,
  lecturas con su foto y datos de sus conexiones. Solo lectura. Lecturas, consumos sin facturar y la «última
  lectura» de cada conexión son solo los del período en que fue titular (desde el día del cambio, inclusive, son del
  nuevo titular).
- **Correo configurable**: SMTP con las variables `EMAIL_*`; sin `EMAIL_HOST` los correos se guardan como archivos en
  `backend/datos/correos/` (útil para probar).

### D49 · Número del medidor
- El medidor tiene su `Code` (identificación interna, inmutable) y además un **número del medidor** (`numero`): el
  grabado en el aparato, alfanumérico (letras, números y `- . /`, sin espacios), guardado en mayúsculas, opcional y
  **único dentro de la institución** cuando se carga. Tampoco puede coincidir con el código de otro medidor (ni un
  código nuevo con el número de otro), porque el cobrador escribe uno u otro para identificarlo.
- El cobrador identifica el medidor escribiendo ese número (o el código, si no tiene número); el servidor también
  acepta el número al recibir una lectura.
- En la lista del recorrido del cobrador se busca **por número de orden o por número del medidor**: unos pocos dígitos
  son el orden de visita (o un número exacto); con letras o desde 4 caracteres se busca dentro del número o código.
- Mapa del recorrido: punto verde = leída (o ya tomada en ese teléfono), rojo = falta; con el número de orden y un
  botón para leer ese medidor.

### D50 · Con deuda, al día y morosa (filtros del padrón y del mapa, sección 8.2)
- **Con deuda**: la conexión tiene consumos liquidados que todavía no están en una factura vigente, o está en una
  factura a crédito (emitida o en trámite) que todavía debe algo.
- **Morosa**: está en una factura a crédito con saldo cuyo vencimiento ya pasó. Tener saldo no es estar en mora: un
  consumo sin facturar o una factura que todavía no venció es deuda, no mora. Como la factura se emite cuando el
  usuario viene a pagar (D37), el consumo sin facturar no vence; cuándo pasa a ser mora queda para la decisión
  pendiente sobre vencimientos, mora, recargos y suspensión.
- **Al día**: ni consumos sin facturar ni facturas con saldo.
- Una factura con varias conexiones cuenta para todas ellas. Filtrar o colorear por deuda exige poder consultar
  cobranzas o facturas (revela quién debe).

### D51 · Recuperar la contraseña por correo (personal de las instituciones)
- «¿Olvidó su contraseña?» en el ingreso: código de institución + usuario → se envía un **código de 6 dígitos** al
  correo cargado en ese usuario. Vence a los 15 minutos y sirve una vez; se guarda solo su hash.
- Mientras haya un código vigente no se envía otro (nadie puede anular el código que el usuario ya recibió ni
  llenarle la casilla). Los errores se suman entre códigos: con 5 en 24 horas el código deja de servir y no se envían
  más hasta que pase el plazo (no se puede probar sin fin). En ese caso la restablece un administrador.
- Cambiar o restablecer la contraseña, o cambiar el correo del usuario, anula el código pendiente.
- La respuesta es siempre la misma (exista o no el usuario, tenga o no correo).
- Con el código se elige la contraseña nueva (con las mismas reglas de seguridad): el usuario queda desbloqueado y se
  cierran todas sus sesiones. Todo queda en la auditoría.
- Sin correo cargado, sigue valiendo D7 (la restablece un administrador). Los usuarios de la plataforma usan el panel
  de la plataforma (`manage.py changepassword` si se pierde la del superusuario).

### D52 · Ticket de lectura para impresora térmica (pedido del cliente, 22/10/2026)
- Después de leer, el cobrador entrega un **ticket** (en lugar del comprobante con foto): institución (nombre, RUC,
  dirección, teléfono), cliente (nombre, C.I./RUC, n.º de cliente, conexión, dirección, medidor), **lectura
  anterior** (n.º de comprobante —o «instalación del medidor»—, fecha y valor), **lectura actual** (n.º, fecha y
  hora, valor leído y consumo) y **aranceles** (conceptos de la liquidación con cantidades y precios, IVA y total).
- PDF angosto de 58 mm (por defecto) u 80 mm, con el largo justo del contenido; el ancho se elige en el teléfono y
  queda recordado. Se imprime con la aplicación de la impresora Bluetooth (compartir/imprimir el PDF).
- Una lectura en revisión no tiene liquidación todavía: el ticket lo dice en lugar de los aranceles.
- Sin «³» ni «×» (las impresoras térmicas no los traen): «m3» y «x». Dice que no es factura ni recibo.
- La oficina conserva el comprobante con foto y también puede sacar el ticket.

---

## Decisiones de negocio pendientes (sección 24)

1. Proveedor de factura electrónica y su documentación API.
2. Modalidad (autoimpresa o electrónica) de cada institución: la carga la plataforma según sus habilitaciones.
3. Vencimientos, mora, recargos y suspensión.
4. Conservación de archivos en los teléfonos: la v1 aplica la política de D29 (confirmar plazos).
5. ~~Servidor de correo para recuperar contraseñas por e-mail.~~ Resuelta: configurable (D48, D51).

Resueltas el 20/10/2026: varias conexiones por cliente (sí, D15); el cobrador no cobra en la v1 y el GPS es obligatorio (D25). Resueltas el 21/10/2026: estructura tarifaria (D31–D33) y facturación varias liquidaciones / pago parcial a crédito (D37) y pagos contado / recibos a crédito (D38).

Pendiente nueva: ¿las conexiones activas sin lectura en el mes pagan igual el mínimo? Hoy solo se liquida lo leído.
