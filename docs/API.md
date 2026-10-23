# API — Koape Aguateras (v1)

Prefijo: `/api/v1/`. Todo en JSON. Errores con el formato `{"detalle": "mensaje"}` (o errores por campo).

## Autenticación

Cabecera `Authorization: Token <token>`. El token se obtiene al ingresar y **define la institución** de
todas las solicitudes: no existe ningún parámetro para elegir institución.

Cabecera opcional `X-Id-Solicitud` (8–64 caracteres alfanuméricos o guiones): se guarda en la auditoría y
vuelve en la respuesta. Si no se manda o es inválida, el servidor genera una.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `auth/ingresar/` | `{codigo_institucion, usuario, contrasena}` → datos de sesión + `token`. Límite: 10 intentos/min por IP. Bloqueo de 15 min tras 5 contraseñas incorrectas. Cualquier error de credenciales da el mismo mensaje. |
| POST | `auth/salir/` | Revoca el token. 204. |
| GET | `auth/yo/` | Usuario, institución, permisos efectivos y vencimiento de la sesión. |
| POST | `auth/cambiar-contrasena/` | `{contrasena_actual, contrasena_nueva}`. Cierra las demás sesiones. |
| POST | `auth/recuperar/` | Sin sesión. `{codigo_institucion, usuario}`: envía un código de 6 dígitos al correo del usuario. Siempre responde 200 con el mismo mensaje. Límite `LIMITE_RECUPERAR_CONTRASENA` (10/hora). |
| POST | `auth/recuperar/confirmar/` | Sin sesión. `{codigo_institucion, usuario, codigo, contrasena_nueva}`: guarda la contraseña, desbloquea y cierra todas las sesiones. Errores `codigo_invalido`, `contrasena_debil`. |

Con contraseña inicial o restablecida (`usuario.debe_cambiar_contrasena = true`) solo responden estos cuatro
endpoints; el resto devuelve 403 «Debe cambiar su contraseña antes de continuar».

## Institución

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `institucion/` | `institucion.ver` o `institucion.editar` | Datos de la institución de la sesión. |
| PATCH | `institucion/` | `institucion.editar` | Nombre, RUC, dirección, teléfono, correo, contacto, zona horaria, configuración regional. Código, estado y modalidad de facturación son de solo lectura. |

## Usuarios, roles y permisos

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `usuarios/?buscar=&pagina=&tamanio=` | `usuarios.administrar` | Lista paginada. |
| POST | `usuarios/` | `usuarios.administrar` | Alta: `{usuario, contrasena, nombre, apellido, correo, activo, es_admin_institucion, roles: [ids]}`. |
| GET/PATCH | `usuarios/{id}/` | `usuarios.administrar` | Detalle y modificación. No hay DELETE: se desactiva con `activo: false`. |
| POST | `usuarios/{id}/restablecer-contrasena/` | `usuarios.administrar` | `{contrasena_nueva}`. |
| GET/POST | `roles/` | `roles.administrar` (lectura también con `usuarios.administrar`) | `{Code, nombre, descripcion, activo, permisos: [códigos]}`. |
| GET/PATCH | `roles/{id}/` | ídem | El `Code` no cambia. No hay DELETE: se desactiva. |
| GET | `permisos/` | `roles.administrar` o `usuarios.administrar` | Catálogo vigente. |

Reglas: solo un administrador institucional da o quita la condición de administrador o modifica a otro
administrador; nadie se desactiva a sí mismo; un rol de otra institución responde «no existe».

## Auditoría

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `auditoria/?desde=&hasta=&accion=&usuario=&entidad=&resultado=&pagina=` | `auditoria.consultar` | Solo lectura, solo la institución de la sesión. |
| GET | `auditoria/{id}/` | ídem | Detalle con `antes`, `despues`, `detalle`, `ip`, `id_solicitud`. |

## Claves: `Code` y `SerNr`

Ningún maestro se expone ni se busca por su id interno. Las rutas de detalle usan el **`Code`** (`clientes/C-0001/`,
también en minúsculas) y las referencias entre registros también (`{"cliente": "C-0001", "barrio": "SAN-ROQUE"}`).
El `Code` es obligatorio al crear, se guarda en mayúsculas (letras, números, `.`, `-`, `_`; máx. 40), es único en
la institución y no se cambia (un PATCH con otro `Code` responde 400). Un `Code` de otra institución responde
«no existe» (400) o 404. Los filtros `zona`, `barrio` y `cliente` también reciben el `Code`.

## Territorio (Fase 2)

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET/POST | `zonas/?activos=1` | `territorio.gestionar` (lectura también con `padron.consultar`, `padron.conexiones` o `mapa.ver`) | `{Code, nombre, color #RRGGBB, poligono GeoJSON, observaciones, activa}`. |
| GET/PATCH | `zonas/{Code}/` | ídem | Sin DELETE: `activa: false` la archiva (auditado; restaurar también). |
| GET/POST | `barrios/?zona=&activos=1` | ídem | `{zona (Code), Code, nombre, poligono, observaciones, activo}`. No se agregan barrios a una zona archivada. |
| GET/PATCH | `barrios/{Code}/` | ídem | Sin DELETE. |

## Padrón (Fase 2)

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `clientes/?buscar=&estado=&incluir_archivados=1` | `padron.consultar` | Paginado; `cantidad_conexiones` no archivadas. |
| POST | `clientes/` | `padron.clientes` | `{Code, nombre, tipo_persona, documento, telefono, correo, direccion_referencia, observaciones}`. |
| GET/PATCH | `clientes/{Code}/` | ídem | `estado: archivado` solo si no tiene conexiones sin archivar. Sin DELETE. |
| GET | `clientes/{Code}/conexiones/` | `padron.consultar` | Conexiones del cliente. |
| GET | `conexiones/?buscar=&estado=a,b&zona=&barrio=&sin_barrio=1&ubicacion=con|sin&sin_medidor=1&cliente=&incluir_archivadas=1` | `padron.consultar` | Paginado. |
| POST | `conexiones/` | `padron.conexiones` | `{Code, cliente, direccion, barrio, latitud, longitud, metodo_ubicacion, precision_metros, fecha_instalacion, estado (en_instalacion/pendiente_ubicacion/activa), observaciones}`. |
| GET/PATCH | `conexiones/{Code}/` | ídem | Detalle con instalaciones, titulares y `transiciones` posibles. PATCH solo dirección, barrio, ubicación, fecha de instalación y observaciones. |
| POST | `conexiones/{Code}/estado/` | `padron.conexiones` | `{estado, motivo}` según las transiciones (D16). |
| POST | `conexiones/{Code}/titular/` | `padron.conexiones` | `{cliente, desde, motivo}`. |
| GET / POST | `conexiones/{Code}/foto-vivienda/` | GET `padron.consultar` · POST `padron.conexiones` | Imagen privada; POST multipart `archivo` (JPG/PNG/WEBP, máx. 8 MB). |
| POST | `conexiones/{Code}/instalar-medidor/` | `padron.medidores` | `{medidor, fecha, lectura_inicial, observaciones}`. |
| POST | `conexiones/{Code}/retirar-medidor/` | `padron.medidores` | `{fecha, lectura_retiro, motivo, estado_medidor, aceptar_lectura_menor}`. Responde `codigo: lectura_menor` si hace falta confirmar. |
| POST | `conexiones/{Code}/sustituir-medidor/` | `padron.medidores` | `{medidor, fecha, lectura_retiro, lectura_inicial, motivo, estado_medidor_retirado, aceptar_lectura_menor}`. |
| GET | `medidores/?buscar=&estado=&instalables=1` | `padron.consultar` | Paginado, con `conexion_actual`. `buscar` busca en código, número, marca y modelo. |
| POST | `medidores/` | `padron.medidores` | `{Code, numero, marca, modelo, unidad, lectura_maxima, observaciones}`. `numero`: el grabado en el medidor, alfanumérico, único en la institución (`codigo: numero_repetido`). |
| GET/PATCH | `medidores/{Code}/` | ídem | El `Code` no cambia; el estado de uno instalado cambia solo al retirarlo. |
| GET | `medidores/{Code}/historial/` | `padron.consultar` | Instalaciones del medidor. |
| GET | `mapa/` (mismos filtros que conexiones) | `mapa.ver` | Zonas, barrios (con polígonos y colores), conexiones con ubicación, `sin_ubicacion`, `total`. |
| GET | `padron/resumen/` | `padron.consultar` | Totales para el inicio. |

## Numeración de facturas y notas de crédito

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET/POST | `puntos-expedicion/?activos=1` | `facturacion.numeracion` (lectura también con `institucion.ver`) | `{Code, establecimiento (3 dígitos), punto (3 dígitos), nombre, direccion, observaciones, activo}`; la respuesta incluye `prefijo` (001-001) y sus `rangos`. |
| GET/PATCH | `puntos-expedicion/{Code}/` | ídem | Establecimiento y punto no cambian si ya emitió documentos. Sin DELETE. |
| GET/POST | `rangos-numeracion/?punto=&tipo=` | ídem | `{Code, punto (Code), tipo_documento (factura/nota_credito), timbrado, desde, hasta, vigencia_desde, vigencia_hasta, activo, observaciones}`. Responde `en_uso` y `agotado`; **nunca** el contador interno. Sin superposición por punto + tipo + timbrado. |
| GET/PATCH | `rangos-numeracion/{Code}/` | ídem | Usado: solo `hasta` (≥ último emitido), vigencia, observaciones y `activo`. Sin DELETE. |

El `SerNr` de cada documento lo asigna el servidor (`tomar_sernr`) al emitirlo; no se envía desde el navegador. Sin
rango disponible responde `codigo: sin_numeracion`.

## Recorridos (Fase 3)

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET/POST | `recorridos/?periodo=AAAA-MM&estado=&incluir_anulados=1` | `recorridos.gestionar` (lectura también con `lecturas.consultar`) | `{Code, nombre, periodo, fecha_desde, fecha_hasta, observaciones}`; responde con `cobradores` y `avance` (`total, leidas, confirmadas, en_revision, pendientes`). |
| GET/PATCH | `recorridos/{Code}/` | ídem | El período no cambia. Sin DELETE. |
| GET | `recorridos/{Code}/conexiones/` | ídem | Conexiones en orden de visita, con medidor y lectura del recorrido. |
| POST | `recorridos/{Code}/agregar-conexiones/` | `recorridos.gestionar` | `{zona}` o `{barrio}` o `{conexiones: [Code…]}` (uno solo). Responde `agregadas`, `sin_medidor`, `en_otro_recorrido`. |
| POST | `recorridos/{Code}/quitar-conexion/` | ídem | `{conexion}`. No si ya tiene lectura en el recorrido. |
| POST | `recorridos/{Code}/ordenar/` | ídem | `{conexiones: [Code…]}` con todas, en el orden de visita. |
| POST | `recorridos/{Code}/asignar-cobrador/` · `retirar-cobrador/` | ídem | `{usuario}` (nombre de usuario con `lecturas.registrar`). |
| POST | `recorridos/{Code}/estado/` | ídem | `{estado, motivo}`: abrir (exige conexiones y cobrador), cerrar, reabrir (motivo), anular (solo planificado, motivo). |
| GET | `recorridos/cobradores/` | ídem | Usuarios que pueden tomar lecturas. |

## Aplicación del cobrador (Fase 3) — permiso `lecturas.registrar`

| Método | Ruta | Descripción |
|---|---|---|
| GET | `cobrador/recorridos/` | Recorridos ABIERTOS asignados al usuario (los demás responden 404). |
| GET | `cobrador/recorridos/{Code}/paquete/` | Todo para trabajar sin conexión: conexiones en orden con titular, dirección, medidor (`medidor` = código, `medidor_numero` = número grabado), capacidad, lectura y fecha anterior, y si ya está leída. |
| GET | `cobrador/recorridos/{Code}/foto-vivienda/{conexion}/` | Foto de la vivienda, solo de conexiones del recorrido. |
| POST | `cobrador/recorridos/{Code}/iniciar/` · `finalizar/` | Registra inicio y fin del cobrador. |
| POST | `cobrador/lecturas/` (multipart) | `id_operacion` (UUID del teléfono), `recorrido`, `medidor` (código o número del medidor), `lectura_actual`, `capturada_en`, `latitud`, `longitud` (obligatorias), `precision_metros`, `comentario`, `foto_origen` (`camara`/`galeria`), `foto` (obligatoria), `adicionales` (hasta 3). 201 nueva · 200 `ya_recibida` (reintento). Responde la lectura y `deudas`. Rechazos (400) con `codigo`: `fuera_de_asignacion` (nunca asignado), `sin_foto`, `sin_gps`, `medidor_inexistente`, `medidor_sin_instalacion`, `recorrido_no_abierto`, `operacion_ajena`. Lo que pudo cambiar sin conexión no se rechaza: queda `requiere_revision` con `motivo_revision` (D27). |
| GET | `cobrador/lecturas/{comprobante}/` · `…/comprobante/` | Sus propias lecturas y el comprobante PDF (con foto). |
| GET | `cobrador/lecturas/{comprobante}/ticket/?ancho=58\|80` | Ticket para impresora térmica (PDF de 58 u 80 mm de ancho): institución, cliente, lectura anterior y actual, consumo y aranceles de la liquidación. También en `lecturas/{comprobante}/ticket/` (oficina). |

## Lecturas en la oficina (Fase 3)

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `lecturas/?periodo=&estado=&recorrido=&conexion=&medidor=&zona=&cobrador=&buscar=` | `lecturas.consultar` | Paginado. |
| GET | `lecturas/{comprobante}/` | ídem | Detalle con `fotos` (`n`, `principal`, `origen`). |
| GET | `lecturas/{comprobante}/fotos/{n}/` · `…/comprobante/` | ídem | Foto privada · comprobante PDF. |
| POST | `lecturas/{comprobante}/autorizar/` | `lecturas.revisar` | `{motivo, consumo?}`: solo «requiere revisión»; si la lectura es menor que la anterior el consumo es obligatorio (`consumo_requerido`). |
| POST | `lecturas/{comprobante}/corregir/` | ídem | `{lectura_actual, motivo}`: recalcula; si queda menor que la anterior pasa a revisión. No si hay lecturas posteriores. |
| POST | `lecturas/{comprobante}/anular/` | ídem | `{motivo}`. No si hay lecturas posteriores confirmadas. |

Filtros nuevos de `conexiones/` y `mapa/`: `lectura=con|sin&periodo=AAAA-MM`, `recorrido=Code`, `cobrador=usuario`.

Filtro de deuda de `conexiones/` y `mapa/` (D50): `deuda=con|al_dia|morosa|sin_facturar`; exige
`cobranzas.consultar` o `facturacion.consultar` (si no, 403). Con esos permisos, cada punto de `mapa/` trae además
`deuda` (`al_dia`, `con` o `morosa`).

## Tarifas y liquidaciones (Fase 4)

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET/POST | `tarifas/` | `tarifas.gestionar` (lectura también con `liquidaciones.consultar` o `padron.conexiones`) | `{Code, nombre, descripcion, por_defecto, activa}`; responde con `versiones` y sus `conceptos`. La primera queda por defecto. |
| GET/PATCH | `tarifas/{Code}/` | ídem | Marcar otra como `por_defecto` desmarca la anterior. La por defecto no se desactiva. |
| POST | `tarifas/{Code}/versiones/` | `tarifas.gestionar` | `{vigente_desde: AAAA-MM, observaciones, conceptos: [{orden, nombre, tipo, cantidad, desde, hasta, precio, porcentaje, iva}]}`. Tipos: `minimo` (cantidad, precio), `excedente` (precio; exige mínimo), `tramo` (desde, hasta?, precio), `por_m3` (precio), `fijo` (precio), `porcentaje` (porcentaje). IVA: `10`, `5`, `exento`. Precios sin IVA. |
| PATCH | `tarifas/{Code}/versiones/{AAAA-MM}/` | ídem | `{conceptos?, observaciones?}`. Los conceptos solo si la versión no se usó en liquidaciones. |
| POST | `tarifas/{Code}/simular/` | lectura | `{periodo, consumo}` → líneas, subtotales por IVA y total (no guarda nada). |
| GET | `liquidaciones/?periodo=&estado=&conexion=&tarifa=&lectura=&buscar=` | `liquidaciones.consultar` | Paginado. |
| GET | `liquidaciones/{numero}/` | ídem | Detalle con líneas, subtotales, IVA, total, tarifa y versión. |
| POST | `liquidaciones/liquidar-pendientes/` | `tarifas.gestionar` | `{periodo?}`: liquida lecturas confirmadas sin liquidar. Responde `liquidadas` y `sin_tarifa`. |
| GET | `liquidaciones-resumen/?periodo=` | `liquidaciones.consultar` | Totales vigentes del período y `sin_liquidar`. |

Las liquidaciones se generan solas al confirmarse una lectura; `conexiones/{Code}/` acepta `tarifa` (Code o null).

## Facturación (Fase 5)

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `facturacion/pendientes/?cliente=Code` | `facturacion.emitir` | Datos del cliente, `pendientes` (liquidaciones vigentes sin factura de sus conexiones), `modalidad`, `dias_vencimiento_credito`, `puntos` activos. |
| POST | `facturas/` | `facturacion.emitir` | `{cliente, liquidaciones: [numero…], condicion: contado\|credito, punto?, observaciones?}`. Una liquidación entera por factura; todas del mismo cliente. Errores: `modalidad_no_configurada`, `proveedor_no_configurado`, `sin_rango`, `ya_facturada`… |
| GET | `facturas/?estado=&condicion=&cliente=&desde=&hasta=&buscar=` | `facturacion.consultar` (o emitir/anular) | Paginado. |
| GET | `facturas/{referencia}/` | ídem | Detalle: número, timbrado, cliente (instantánea), líneas, subtotales IVA incluido, IVA 5/10, total, liquidaciones y estado electrónico. |
| GET | `facturas/{referencia}/pdf/` | ídem | PDF de la factura autoimpresa. |
| POST | `facturas/{referencia}/anular/` | `facturacion.anular` | `{motivo}`. Solo autoimpresa emitida; libera sus liquidaciones. |
| POST | `facturas/{referencia}/consultar-estado/` | `facturacion.emitir` | Factura electrónica: consulta al proveedor (tras un corte o en proceso). |
| POST | `facturas/{referencia}/reintentar/` | `facturacion.emitir` | Reenvía con el mismo `id_solicitud` (solo pendiente o error recuperable). |

`POST facturas/` con `condicion: contado` exige además `forma_pago` (Code) y, si esa forma lo pide, `referencia_externa`:
el pago queda registrado con la factura. Las facturas responden `pagado`, `saldo`, `estado_cobro` (pagada, parcial,
pendiente, vencida) y `pagos`; el listado acepta `con_saldo=1`. Una factura con recibos vigentes no se anula
(`tiene_recibos`); anular una contado revierte su pago.

`cobrador/lecturas/` responde además `deudas`: `pendientes_de_facturar` y `facturas` a crédito con saldo y días de atraso.

## Pagos y recibos (Fase 6)

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET/POST | `formas-pago/` | `cobranzas.formas_pago` (lectura con `cobranzas.registrar`, `cobranzas.consultar` o `facturacion.emitir`) | `{Code, nombre, tipo: efectivo\|transferencia\|pos\|otro, requiere_referencia, orden, activa}`. |
| PATCH | `formas-pago/{Code}/` | ídem | El `Code` no cambia; se desactiva, no se borra. |
| GET | `cobranzas/estado-cuenta/?cliente=Code` | `cobranzas.registrar` (o consultar/anular) | Facturas a crédito con saldo (la vencida más antigua primero), `total_saldo`, `aplicacion_pagos`, `formas_pago`. |
| POST | `recibos/` | `cobranzas.registrar` | `{cliente, importe, forma_pago, referencia_externa?, observaciones?, clave, aplicaciones?: [{factura: referencia, importe}]}`. La suma aplicada = importe (sin saldo a favor). Sin `aplicaciones` solo si la institución usa reparto automático. Misma `clave` → mismo recibo (reintento). Errores: `supera_saldo`, `reparto_distinto`, `reparto_requerido`, `sin_saldo`, `falta_referencia`, `clave_repetida`. |
| GET | `recibos/?buscar=&estado=&cliente=&forma_pago=&desde=&hasta=` | `cobranzas.consultar` (o registrar/anular) | Paginado. |
| GET | `recibos/{numero}/` · `recibos/{numero}/pdf/` | ídem | Detalle con aplicaciones (saldo anterior, aplicado, saldo) y PDF. |
| POST | `recibos/{numero}/anular/` | `cobranzas.anular` | `{motivo}`. El pago queda revertido (no se borra) y las facturas recuperan su saldo. |
| GET | `pagos/?cliente=&origen=&estado=&forma_pago=&cobrador=&desde=&hasta=` | `cobranzas.consultar` (o registrar/anular) | Historial de cobranzas: contado y recibos, confirmados y revertidos. |
| GET | `pagos/{referencia}/` | ídem | Detalle de un pago (P-XXXXXXXX). |

`institucion/` acepta `aplicacion_pagos`: `manual` (por defecto) o `automatica`.

## Caja y gastos (Fase 7)

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `caja/mi-sesion/` | `caja.operar` | `{sesion, cajas_libres}`: la sesión abierta de quien consulta (con `resumen` por forma de pago) o null. |
| POST | `caja/mi-sesion/` | `caja.operar` | `{caja: Code, saldo_inicial}` abre la caja. Errores: `ya_abierta`, `caja_ocupada`. |
| GET | `sesiones-caja/?estado=&caja=&responsable=&desde=&hasta=` | `caja.operar` (solo las propias) o `caja.supervisar` (todas) | Paginado, con `resumen` y `declaraciones`. |
| GET | `sesiones-caja/{referencia}/` · `movimientos/` · `pdf/` | ídem | Detalle, movimientos (con su origen) y arqueo PDF. |
| POST | `sesiones-caja/{referencia}/cerrar/` | `caja.operar` (el responsable) o `caja.supervisar` | `{declarados: [{forma_pago, importe}], observaciones}`. Todas las formas con movimiento deben declararse; con diferencias queda `en_revision` y exige observaciones. |
| POST | `sesiones-caja/{referencia}/revisar/` | `caja.supervisar` | `{comentario}`: en revisión → cerrada. |
| GET/POST/PATCH | `cajas/` · `cajas/{Code}/` | `caja.supervisar` (lectura `caja.operar`) | `{Code, nombre, activa}` y `abierta_por`. |
| GET/POST/PATCH | `categorias-gasto/` · `{Code}/` | `gastos.confirmar` (lectura registrar/consultar) | `{Code, nombre, activa}`. |
| GET/POST | `gastos/?estado=&categoria=&sesion=&desde=&hasta=&buscar=` | `gastos.registrar` (lectura `gastos.consultar`, `gastos.confirmar`) | `{fecha, motivo, importe, categoria, forma_pago, numero_comprobante?, beneficiario, responsable?, observaciones?}`. |
| PATCH | `gastos/{referencia}/` | `gastos.registrar` | Solo sin confirmar; con boleta impresa no cambian fecha, importe, motivo, beneficiario ni responsable. |
| POST | `gastos/{referencia}/confirmar/` | `gastos.confirmar` | Egreso único en la caja abierta de quien confirma (reintento = sin cambios). |
| POST | `gastos/{referencia}/anular/` | `gastos.confirmar` | `{motivo}`; si estaba confirmado registra el ingreso compensatorio. |
| POST | `gastos/{referencia}/adjuntos/` | `gastos.registrar` | multipart `archivo` (JPG, PNG, WEBP o PDF) y `tipo`: `comprobante` o `boleta_firmada`. |
| GET | `gastos/{referencia}/adjuntos/{codigo}/` | lectura | El archivo (privado). |
| POST · GET | `gastos/{referencia}/boleta/` · `boleta/pdf/` | `gastos.registrar` · lectura | Genera (una vez) la boleta interna numerada y su PDF. |

Cobrar (`POST facturas/` contado y `POST recibos/`) exige la caja abierta de quien cobra (`caja_cerrada`).

## Informes (Fase 8)

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `informes/` | sesión | Catálogo de los informes que el usuario puede ver: `{codigo, titulo, grupo, definicion, filtros, agrupaciones}`. |
| GET | `informes/panel/` | sesión | Indicadores del inicio por sección (solo las que el usuario puede ver), con `definicion` y `enlace`. |
| GET | `informes/{codigo}/?filtros` | el del informe | `{columnas: [{clave, titulo, tipo}], filas, totales, filtros}`. Filtros: `desde`, `hasta` (AAAA-MM-DD; por defecto el mes en curso), `periodo_desde`, `periodo_hasta` (AAAA-MM; por defecto los últimos 12), `zona`, `barrio` (Code), `cobrador` (usuario), `estado`, `agrupar`. |
| GET | `informes/{codigo}/?formato=xlsx` · `csv` | ídem | Descarga; queda en la auditoría. CSV con «;» y BOM UTF-8. |

Informes: `conexiones`, `lecturas`, `consumo`, `liquidaciones`, `facturas` (agrupar `dia`/`mes`), `saldos_clientes`,
`antiguedad_deuda`, `recaudacion` (agrupar `fecha`/`cobrador`/`forma`), `gastos`, `cajas`, `integraciones`. La
definición de cada uno viaja en la respuesta (`definicion`).

## Integraciones (Fase 8): API para otros sistemas

**Autenticación de aplicaciones.** El administrador de la institución crea una credencial
(`integraciones/credenciales/`) y recibe UNA vez la clave `kpa_<identificador>_<secreto>`. El otro sistema la envía en
cada solicitud:

```
GET /api/v1/clientes/?buscar=perez
Authorization: Clave kpa_ab12cd34_…
```

- **Solo lectura** (v1): cualquier método distinto de GET/HEAD/OPTIONS responde 403. Tampoco puede usar `auth/` ni
  `integraciones/`.
- **Permisos por institución y recurso**: la credencial ve SOLO su institución y solo lo que permitan sus permisos de
  consulta (`padron.consultar`, `mapa.ver`, `lecturas.consultar`, `liquidaciones.consultar`, `facturacion.consultar`,
  `cobranzas.consultar`, `gastos.consultar`, `caja.supervisar`). Usa las mismas rutas, filtros y reglas que la
  aplicación (no hay lógica duplicada).
- **Revocable y con vencimiento**: revocada o vencida responde 401.
- **Límite de uso**: `limite_por_minuto` (por defecto 60); al superarlo responde 429 con `Retry-After`.
- **Registro**: cada solicitud queda guardada (método, ruta, respuesta, IP, duración, id de solicitud) y se ve en
  `integraciones/credenciales/{identificador}/registro/`.
- **Errores**: `{"detalle": "..."}` (los errores de reglas de negocio agregan `codigo`) con 400 (validación), 401 (credencial), 403 (permiso o
  escritura), 404 (no existe o es de otra institución), 429 (límite). Cada respuesta trae `X-Id-Solicitud`.
- **Paginación**: `?pagina=N` (50 por página): `{count, next, previous, results}`.
- **Identificadores**: nunca ids internos; se usa el `Code` de los maestros y los números de documento.

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `integraciones/permisos/` | `integraciones.administrar` | Permisos que se pueden dar a una credencial. |
| GET/POST | `integraciones/credenciales/` | ídem | Crear: `{nombre, permisos: [...], limite_por_minuto?, expira_en?}` → incluye `clave` (una sola vez). |
| POST | `integraciones/credenciales/{identificador}/revocar/` | ídem | `{motivo}`. |
| GET | `integraciones/credenciales/{identificador}/registro/` | ídem | Últimas 200 solicitudes. |

**Preparado para más adelante** (sección 16): las escrituras desde otros sistemas se habilitarán cuando se defina la
integración concreta, reutilizando los servicios de dominio y sus claves de idempotencia (ej. `clave` de los recibos).

## Portal de abonados

Para las personas (abonados), no para el personal. Una cuenta por número de documento, con sus datos en todas las
instituciones que tienen el portal activo (D48). Las rutas privadas usan `Authorization: Portal <token>`; el token del
personal no sirve aquí y el del portal no sirve en el resto de la API.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `portal/solicitar-pin/` | `{documento, correo}`. Siempre responde 200 con el mismo mensaje; envía el PIN solo si el correo está en el padrón con ese documento. `codigo: espere` si se pidió otro hace menos de 1 minuto. |
| POST | `portal/ingresar/` | `{usuario (correo o documento), clave (contraseña o PIN)}` → `{token, debe_cambiar_clave, nombre}`. Errores `ingreso_invalido`, `bloqueada`, `correo_compartido`. |
| GET | `portal/yo/` | Datos de la cuenta. |
| POST | `portal/cambiar-clave/` | `{nueva, actual?}` (`actual` no se pide después de ingresar con PIN). Cierra las demás sesiones. |
| POST | `portal/salir/` | Cierra la sesión. |
| GET | `portal/resumen/` | Por institución: conexiones, deuda, saldo de facturas, consumo sin facturar. |
| GET | `portal/{institucion}/deuda/` · `facturas/` · `pagos/` · `lecturas/` · `conexiones/` | Lo propio en esa institución (404 si no es cliente ahí). Hasta cambiar la contraseña responden 403. |
| GET | `portal/{institucion}/facturas/{referencia}/pdf/` · `recibos/{numero}/pdf/` · `lecturas/{comprobante}/foto/` | Documentos propios. |

Correo: SMTP con `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`/`EMAIL_USE_SSL`
y `CORREO_REMITENTE`; sin `EMAIL_HOST` se guardan como archivos en `backend/datos/correos/`.

## Otros

| Método | Ruta | Descripción |
|---|---|---|
| GET | `salud/` | `{"estado": "ok"}` sin tocar datos (monitoreo). |

## Catálogo de permisos

| Código | Descripción |
|---|---|
| `institucion.ver` | Ver los datos de la institución |
| `institucion.editar` | Editar los datos de la institución |
| `usuarios.administrar` | Administrar usuarios y sus roles |
| `roles.administrar` | Administrar roles y permisos |
| `auditoria.consultar` | Consultar la auditoría de la institución |
| `territorio.gestionar` | Administrar zonas y barrios (y dibujar sus polígonos) |
| `facturacion.numeracion` | Configurar puntos de expedición y rangos de numeración (SerNr) |
| `recorridos.gestionar` | Armar recorridos, asignar cobradores, abrirlos y cerrarlos |
| `lecturas.consultar` | Consultar lecturas, sus fotos y comprobantes |
| `lecturas.registrar` | Tomar lecturas en los recorridos asignados (aplicación del cobrador) |
| `facturacion.emitir` | Facturar en caja (y consultar o reintentar facturas electrónicas) |
| `facturacion.consultar` | Consultar facturas e imprimirlas |
| `facturacion.anular` | Anular facturas autoimpresas |
| `cobranzas.registrar` | Cobrar facturas a crédito y emitir recibos |
| `cobranzas.consultar` | Consultar pagos, recibos y saldos de los clientes |
| `cobranzas.anular` | Anular recibos (revierte el pago, con motivo) |
| `cobranzas.formas_pago` | Configurar las formas de pago |
| `caja.operar` | Abrir y cerrar su propia caja (necesario para cobrar) |
| `caja.supervisar` | Ver todas las cajas, revisar diferencias y administrar las cajas |
| `gastos.consultar` | Consultar gastos y sus comprobantes |
| `gastos.registrar` | Registrar gastos, adjuntar comprobantes e imprimir la boleta interna |
| `gastos.confirmar` | Confirmar gastos (salen de su caja), anularlos y configurar sus categorías |
| `integraciones.administrar` | Crear y revocar credenciales para que otros sistemas consulten la API |
| `lecturas.revisar` | Autorizar excepciones, corregir y anular lecturas |
| `tarifas.gestionar` | Configurar tarifas, sus versiones y conceptos; liquidar lecturas pendientes |
| `liquidaciones.consultar` | Consultar liquidaciones e importes |
| `padron.consultar` | Consultar clientes, conexiones y medidores |
| `padron.clientes` | Administrar clientes (titulares) |
| `padron.conexiones` | Administrar conexiones: ubicación, estado, titular y fotos |
| `padron.medidores` | Administrar medidores e instalarlos, retirarlos o sustituirlos |
| `mapa.ver` | Ver el mapa completo de conexiones |

Cada fase agrega sus permisos en `backend/apps/identidad/catalogo_permisos.py`.
