import type { ReactNode } from 'react'
import { Encabezado } from '../componentes/Encabezado'

/**
 * Manual para quien usa el sistema día a día (no para programadores).
 * Regla de las convenciones: cada módulo nuevo suma su sección acá en el mismo trabajo.
 */
function Seccion({ numero, titulo, abierta = false, children }: { numero: number; titulo: string; abierta?: boolean; children: ReactNode }) {
  return (
    <details open={abierta} className="tarjeta group">
      <summary className="cursor-pointer px-5 py-4 font-titulo text-lg font-bold">{numero}. {titulo}</summary>
      <div className="space-y-3 px-5 pb-5 text-sm leading-relaxed">{children}</div>
    </details>
  )
}

const Tip = ({ children }: { children: ReactNode }) => (
  <div className="rounded-lg border-l-4 border-koape-amarillo bg-koape-amarillo/10 px-3 py-2">💡 {children}</div>
)
const Alerta = ({ children }: { children: ReactNode }) => (
  <div className="rounded-lg border-l-4 border-koape-rojo bg-koape-rojo/5 px-3 py-2">⚠ {children}</div>
)
const Maqueta = ({ children }: { children: ReactNode }) => (
  <div className="rounded-lg border border-dashed border-koape-gris bg-koape-fondo p-3 font-mono text-xs">{children}</div>
)

export function Manual() {
  return (
    <div className="max-w-4xl space-y-3">
      <Encabezado titulo="Manual de usuario" descripcion="Cómo usar el sistema, sección por sección." />

      <Seccion numero={1} titulo="Ingresar al sistema" abierta>
        <p>Para ingresar se necesitan tres datos: el <b>código de la institución</b> (lo da la plataforma, por ejemplo <code>JUNTA-SL</code>), su <b>usuario</b> y su <b>contraseña</b>.</p>
        <Maqueta>Código de institución: JUNTA-SL<br />Usuario: maria<br />Contraseña: ••••••••</Maqueta>
        <p>La primera vez, o después de que un administrador le restablezca la contraseña, el sistema le pide cambiarla antes de seguir.</p>
        <Alerta>Después de 5 intentos fallidos el usuario queda bloqueado 15 minutos.</Alerta>
        <p>¿Olvidó la contraseña? En la pantalla de ingreso, <b>«¿Olvidó su contraseña?»</b>: escriba el código de la institución y su usuario, y le llega un <b>código de 6 dígitos</b> al correo cargado en su usuario (vale 15 minutos). Con ese código elige una contraseña nueva; también lo desbloquea. Si su usuario no tiene correo, pídale al administrador que se la restablezca (y que cargue su correo en <b>Usuarios</b>).</p>
        <Tip>La sesión dura 12 horas. Al cerrar la pestaña del navegador hay que volver a ingresar.</Tip>
      </Seccion>

      <Seccion numero={2} titulo="Datos de la institución">
        <p>Menú <b>Institución</b>: nombre, RUC, dirección, teléfono, correo y datos de contacto. Quien tenga el permiso «Editar los datos de la institución» puede modificarlos; el resto solo los ve.</p>
        <Alerta>El código de la institución, su estado y la modalidad de facturación los define la plataforma: no se cambian desde acá.</Alerta>
      </Seccion>

      <Seccion numero={3} titulo="Usuarios">
        <p>Menú <b>Usuarios → Nuevo usuario</b>. Complete el usuario, una contraseña inicial y elija sus roles. Pásele la contraseña inicial a la persona: al ingresar deberá cambiarla.</p>
        <ul className="list-disc pl-5">
          <li><b>Desactivar</b>: en Editar, destilde «Activo». La persona ya no puede ingresar y se cierran sus sesiones. Sus registros quedan.</li>
          <li><b>Restablecer contraseña</b>: para quien la olvidó. Se cierran sus sesiones y deberá cambiarla al ingresar.</li>
          <li><b>Administrador institucional</b>: tiene todos los permisos. Solo otro administrador puede dar o quitar esa condición.</li>
        </ul>
        <Alerta>Los usuarios no se borran: se desactivan. Así queda siempre quién hizo cada cosa.</Alerta>
      </Seccion>

      <Seccion numero={4} titulo="Roles y permisos">
        <p>Un <b>rol</b> es un conjunto de permisos (por ejemplo «Cajero» o «Supervisor»). A cada usuario se le asignan uno o varios roles.</p>
        <p>La institución arranca con dos roles: <b>Cobrador</b> (sus permisos se completan cuando se habilite el módulo de lecturas) y <b>Consulta</b> (solo ve los datos de la institución).</p>
        <Tip>Si un rol ya no se usa, desactívelo: sus usuarios pierden esos permisos en el momento.</Tip>
      </Seccion>

      <Seccion numero={5} titulo="Auditoría">
        <p>Menú <b>Auditoría</b>: muestra quién hizo qué y cuándo (ingresos, ingresos fallidos, altas y cambios de usuarios y roles, cambios en los datos de la institución), con los datos de antes y después.</p>
        <p>Filtre por fechas, acción, usuario o resultado. Con <b>Ver</b> se abre el detalle completo.</p>
        <Tip>Varios «Ingreso fallido» seguidos con el mismo usuario pueden indicar que alguien intenta adivinar una contraseña.</Tip>
        <Alerta>La auditoría no se puede modificar ni borrar.</Alerta>
      </Seccion>

      <Seccion numero={6} titulo="Zonas y barrios">
        <p>Menú <b>Padrón → Zonas y barrios</b>. Primero se crean las <b>zonas</b> (con su código, un nombre y un color para el mapa) y dentro de cada zona sus <b>barrios</b>. Cada barrio pertenece a una sola zona.</p>
        <p>Para dibujar el límite de una zona: en la zona, <b>Editar → Dibujar polígono</b>, un clic en el mapa por cada esquina y <b>Terminar</b>. Las demás zonas se ven punteadas de fondo para no superponerlas.</p>
        <Maqueta>Zona «Centro» (azul) ▸ Barrios: San Roque · La Encarnación · Catedral</Maqueta>
        <Tip>Si una zona o un barrio ya no se usa, destilde «Activa/Activo»: queda archivado, no se ofrece para conexiones nuevas y sigue en el historial.</Tip>
      </Seccion>

      <Seccion numero={7} titulo="Clientes (titulares)">
        <p>Menú <b>Padrón → Clientes → Nuevo cliente</b>. Cargue siempre el <b>código</b> del cliente (por ejemplo <code>C-0001</code>): es su clave, no se repite en la institución y no se cambia después. El documento es opcional y no identifica al cliente: puede faltar o repetirse.</p>
        <p>Un cliente puede tener <b>varias conexiones</b> (por ejemplo, su casa y un local). Con <b>Conexiones</b> se ven las suyas y se puede crear una nueva.</p>
        <Alerta>Para archivar un cliente, antes hay que archivar sus conexiones.</Alerta>
      </Seccion>

      <Seccion numero={8} titulo="Conexiones">
        <p>Menú <b>Padrón → Conexiones → Nueva conexión</b>: elija el titular, el barrio, la dirección y marque la ubicación de la vivienda en el mapa (o use el GPS del teléfono). Si no sabe la ubicación, deje el estado «Pendiente de ubicación».</p>
        <p>En la ficha de cada conexión se edita la dirección y la ubicación, se sube la <b>foto de la vivienda</b> (desde el celular abre la cámara), se cambia el <b>estado</b> y el <b>titular</b>, y se ve el historial de medidores y titulares.</p>
        <Maqueta>En instalación → Activa ⇄ Suspendida → Desconectada → Archivada</Maqueta>
        <Tip>Suspender o desconectar una conexión no borra su deuda ni su historial. Todo cambio de estado pide un motivo y queda en la auditoría.</Tip>
        <Alerta>El GPS del navegador solo funciona con la dirección segura (https). En la red local sin https, marque el punto en el mapa.</Alerta>
      </Seccion>

      <Seccion numero={9} titulo="Medidores">
        <p>Menú <b>Padrón → Medidores</b>: se cargan los medidores físicos con su <b>código</b> (identificación interna), el <b>número del medidor</b> (el que está grabado en el aparato, con letras y números, ej. A23057X), marca, modelo y la lectura máxima (ej. 99999). Quedan «Disponibles».</p>
        <p>Se instalan desde la ficha de la conexión: <b>Instalar medidor</b>, con la fecha y la lectura inicial. Cada conexión tiene un solo medidor vigente.</p>
        <p>Para cambiarlo: <b>Sustituir</b> — se carga la lectura final del medidor viejo y la inicial del nuevo en un solo paso. El viejo queda en el historial con sus fechas y lecturas, y se puede marcar como dañado o dado de baja.</p>
        <Tip>Con <b>Historial</b> se ve en qué conexiones estuvo cada medidor. El código no se cambia después del alta; el número del medidor sí se puede corregir, pero no puede repetirse en otro medidor de la institución. El cobrador busca e identifica los medidores por ese número.</Tip>
        <Alerta>Si la lectura final es menor que la inicial (el contador volvió a cero), el sistema pide confirmarlo y explicar el motivo.</Alerta>
      </Seccion>

      <Seccion numero={10} titulo="Mapa">
        <p>Menú <b>Padrón → Mapa</b>: muestra las zonas con sus colores y cada conexión como un punto. Al tocar un punto se ve el titular, la dirección y el medidor, y se abre su ficha.</p>
        <p>Se puede filtrar por zona, barrio, estado (tocando los botones de colores), conexiones sin medidor, lectura del período, recorrido, cobrador y <b>deuda</b>, y colorear los puntos por estado, por zona o por deuda.</p>
        <p>Deuda (también en <b>Conexiones</b>; solo para quien puede consultar cobranzas o facturas): <b>con deuda</b> = tiene consumo sin facturar o una factura a crédito con saldo; <b>morosa</b> = tiene una factura a crédito <b>vencida</b> con saldo; <b>al día</b> = no debe nada. Deber no es lo mismo que estar en mora.</p>
        <Tip>Debajo del mapa se indica cuántas conexiones no tienen ubicación: búsquelas en Conexiones con el filtro «Sin ubicación».</Tip>
      </Seccion>

      <Seccion numero={11} titulo="Códigos de los registros">
        <p>Clientes, conexiones, medidores, zonas, barrios, roles y puntos de expedición se identifican por su <b>código</b>, que carga siempre el usuario: letras, números, puntos o guiones, sin espacios (se guarda en mayúsculas). Es único dentro de la institución y <b>no se cambia</b> después del alta, porque lo usan el historial, la auditoría y los enlaces.</p>
        <Maqueta>Cliente C-0001 · Conexión CX-0001 · Medidor SN-48213 · Zona NORTE · Barrio SAN-ROQUE</Maqueta>
        <p>El <b>nombre de usuario</b> tampoco se cambia después de creado el usuario.</p>
        <Tip>Defina una costumbre para los códigos antes de cargar el padrón (por ejemplo, el número de la planilla de papel), así todos los usuarios cargan igual.</Tip>
      </Seccion>

      <Seccion numero={12} titulo="Puntos de expedición y numeración de facturas">
        <p>Menú <b>Administración → Puntos de expedición</b>. Cada lugar desde donde se emiten facturas es un <b>punto</b> (establecimiento y punto, por ejemplo <code>001-001</code> la oficina y <code>001-002</code> la caja móvil). Una institución puede tener varios.</p>
        <p>Dentro de cada punto se cargan los <b>rangos de numeración</b> por tipo de documento (factura o nota de crédito): timbrado, «desde» y «hasta» y, si corresponde, la vigencia. Cada documento toma su número (<b>SerNr</b>) del rango activo y vigente de su punto, en orden; cuando un rango se agota sigue con el próximo.</p>
        <Maqueta>001-001 · Oficina central ▸ FAC-2026 · Factura · timbrado 12345678 · 1 – 5.000 · En uso</Maqueta>
        <Tip>Cargue el rango nuevo antes de que se agote el actual: sin numeración disponible el sistema no emite el documento.</Tip>
        <Alerta>Los rangos del mismo punto, tipo y timbrado no pueden superponerse. Un rango ya usado solo se puede ampliar («hasta»), cambiar su vigencia o desactivar.</Alerta>
      </Seccion>

      <Seccion numero={13} titulo="Recorridos de lectura">
        <p>Menú <b>Lecturas → Recorridos → Nuevo recorrido</b>: código, nombre y <b>período</b> (mes). Después, en la ficha del recorrido:</p>
        <p>1. <b>Agregar conexiones</b> por zona, por barrio o escribiendo sus códigos (entran las que están en servicio y tienen medidor). 2. Ordenarlas con ▲ ▼ en el <b>orden de visita</b>. 3. <b>Asignar</b> uno o más cobradores. 4. <b>Abrir</b> el recorrido: recién ahí lo ven en el celular.</p>
        <Maqueta>Centro octubre · CENTRO-10 · 2026-10 · Abierto · 18 de 40 leídas · 2 en revisión</Maqueta>
        <Tip>Una conexión está en un solo recorrido por mes, así dos cobradores no leen la misma.</Tip>
        <Alerta>Al terminar el mes, <b>Cierre</b> el recorrido. Si hace falta, se reabre con un motivo.</Alerta>
      </Seccion>

      <Seccion numero={14} titulo="Aplicación del cobrador (celular)">
        <p>El cobrador ingresa con su usuario desde el navegador del celular y entra directo a su aplicación. Conviene <b>instalarla</b>: menú del navegador → «Instalar aplicación» o «Agregar a pantalla principal».</p>
        <p>Para leer: elegir el recorrido → <b>Tomar lectura</b> → escribir el número del medidor → <b>sacar la foto</b> del medidor (obligatoria) → recién entonces aparecen el titular y la lectura anterior → escribir la lectura actual → <b>Confirmar</b>. La ubicación GPS es obligatoria.</p>
        <p>En la lista del recorrido se puede <b>buscar por número de orden</b> (ej. «12») <b>o por número del medidor</b> (ej. «A231»), y con <b>Mapa</b> se ven los puntos del recorrido: <b>verde</b> los ya leídos y <b>rojo</b> los que faltan, con su número de orden. Tocando un punto rojo → <b>Leer este medidor</b>.</p>
        <p>Al terminar, <b>🧾 Imprimir ticket</b>: un ticket para la impresora térmica con los datos de la junta y del cliente, la lectura anterior (número, fecha y valor), la lectura actual (número, fecha, valor leído y consumo) y los aranceles con el total. Se abre como PDF: compártalo o imprímalo con la aplicación de la impresora Bluetooth. El ancho del papel (58 u 80 mm) se elige en <b>Lecturas</b> y el teléfono lo recuerda. También se puede volver a sacar desde <b>Lecturas</b>.</p>
        <Maqueta>Medidor A23057X → 📷 Foto → María Benítez · anterior 1.250 → actual 1.262,5 → ✓ Comprobante L-7KQ3M2XA</Maqueta>
        <Tip>Sin señal se puede seguir trabajando: las lecturas quedan guardadas en el teléfono con sus fotos y se envían solas al volver la conexión. Descargue el recorrido (abrirlo una vez con señal) antes de salir.</Tip>
        <Alerta>No borre los datos del navegador ni cierre sesión con lecturas sin enviar. El GPS y la instalación de la aplicación necesitan la dirección segura (https).</Alerta>
      </Seccion>

      <Seccion numero={15} titulo="Revisión de lecturas">
        <p>Menú <b>Lecturas → Lecturas</b>. Filtre por período y estado «Requiere revisión». Quedan en revisión, sin consumo, las lecturas menores que la anterior, las repetidas del mismo mes y las que llegaron después de un cambio de medidor o del cierre del recorrido.</p>
        <p>En cada lectura se ven la foto, el GPS y la distancia a la conexión. Se puede <b>Autorizar</b> (si es menor que la anterior, usted indica el consumo), <b>Corregir</b> el número leído o <b>Anular</b>. Todo pide motivo y queda en la auditoría.</p>
        <Tip>Con <b>Comprobante PDF</b> se imprime el comprobante de la lectura. No es una factura ni un recibo.</Tip>
        <Alerta>Una lectura no se corrige ni se anula si ya hay lecturas posteriores de ese medidor. La galería del teléfono solo se acepta si se habilita en <b>Institución</b>.</Alerta>
      </Seccion>

      <Seccion numero={16} titulo="Tarifas">
        <p>Menú <b>Tarifas → Tarifas</b>. Cree una tarifa por <b>tipo de conexión</b> (Residencial, Comercial, Social…). La marcada «por defecto» la usan las conexiones sin tipo asignado; el tipo de cada conexión se elige en su ficha.</p>
        <p>Cada tarifa tiene <b>versiones</b> con su vigencia (desde un mes) y sus <b>conceptos</b>, cargados <b>sin IVA</b>:</p>
        <p>• <b>Consumo mínimo</b>: los m³ del mínimo a su precio, se cobran se usen o no. • <b>Excedente</b>: precio por cada m³ por encima del mínimo. • <b>Tramos</b>, <b>precio por m³</b> y <b>cargo fijo</b> si los necesita. • <b>Porcentaje</b>: por ejemplo la tasa <b>ERSSAN</b> (2 % del servicio sin impuestos, exenta). Cada concepto lleva su IVA: 10 %, 5 % o exento.</p>
        <Maqueta>15 m³ → mínimo 10 m³ × 2.500 = 25.000 · excedente 5 × 3.000 = 15.000 · ERSSAN 2 % = 800 (exento) · IVA 10 % = 4.000 · total 44.800</Maqueta>
        <Tip>Use <b>Simular</b> para probar la tarifa con un consumo antes de que se apliquen.</Tip>
        <Alerta>Una versión ya usada en liquidaciones no se modifica: para cambiar precios cree una versión nueva con vigencia desde el mes siguiente. Así lo ya liquidado no cambia. Las juntas de saneamiento sin fines de lucro pueden estar exoneradas de IVA (consulte a su contador): en ese caso marque los conceptos como «Exento».</Alerta>
      </Seccion>

      <Seccion numero={17} titulo="Liquidaciones">
        <p>Cada lectura confirmada se <b>liquida sola</b> con la tarifa vigente en su mes: queda el detalle de conceptos, cantidades, precios, IVA y total. Si después se corrige o anula la lectura, la liquidación anterior queda anulada en el historial y se calcula una nueva.</p>
        <p>Menú <b>Tarifas → Liquidaciones</b>: totales del mes (gravado, IVA, exento, total) y el detalle de cada una.</p>
        <Tip>Si una lectura se confirmó cuando todavía no había tarifa vigente, queda «sin liquidar»: cargue la tarifa y use <b>Liquidar pendientes</b>.</Tip>
        <Alerta>Una liquidación no es una factura: se factura cuando el usuario viene a pagar (sección 18).</Alerta>
      </Seccion>

      <Seccion numero={18} titulo="Facturar (caja)">
        <p>Cuando el usuario viene a pagar: menú <b>Facturación → Facturar (caja)</b>, busque al titular y aparecen sus <b>liquidaciones pendientes</b> (todas marcadas). Puede facturar <b>varias juntas</b> en una sola factura; cada liquidación se factura <b>entera y una sola vez</b>.</p>
        <p>Elija la <b>condición</b>: <b>Contado</b> o <b>Crédito</b> (vence a los días que fije la institución en <b>Institución → Lecturas y facturación</b>; 30 por defecto), el <b>punto de expedición</b> si hay varios, y <b>Emitir</b>. El número (001-001-0000001) sale del rango vigente del punto y no se repite.</p>
        <Maqueta>Liquidación de octubre 44.800 + noviembre 41.300 → una factura de 86.100</Maqueta>
        <p><b>Contado</b>: elija también la <b>forma de pago</b> (efectivo, transferencia, POS…; las que piden referencia exigen el número de la operación). El pago queda registrado junto con la factura, que sale <b>pagada</b>.</p>
        <Tip>Si el usuario quiere pagar <b>en partes</b>, emita la factura <b>a crédito</b> y cóbrela después con recibos (sección 20).</Tip>
        <Alerta>Cargue el RUC o C.I. del titular en <b>Clientes</b> antes de facturar si lo necesita en la factura: lo que se imprime queda fijo.</Alerta>
      </Seccion>

      <Seccion numero={19} titulo="Facturas: imprimir, anular y factura electrónica">
        <p>Menú <b>Facturación → Facturas</b>: búsqueda por número, cliente o RUC, y filtros por estado, condición y fechas. En la ficha: <b>Imprimir (PDF)</b> de la factura autoimpresa, con timbrado, columnas exentas / 5 % / 10 % y liquidación del IVA.</p>
        <p><b>Anular</b> (con motivo): la factura queda en el historial con su número y sus liquidaciones vuelven a quedar para facturar. Si era contado, su pago queda <b>revertido</b>; si tiene cobros con recibo, primero hay que anular esos recibos.</p>
        <p>Cada factura muestra lo <b>pagado</b>, su <b>saldo</b> y el estado del cobro: impaga, pago parcial, pagada o vencida. Con «Solo con saldo pendiente» la lista sirve de cuentas por cobrar.</p>
        <p><b>Factura electrónica</b>: se habilita cuando la institución elige su proveedor. Si el envío se corta, la factura queda en «Estado desconocido» y se usa <b>Consultar estado</b> (nunca se vuelve a emitir a ciegas); si el proveedor la rechaza, las liquidaciones se liberan.</p>
        <Alerta>El formato de la factura autoimpresa usa los datos de uso general en Paraguay: hágalo revisar por su contador con su autorización de autoimpresor antes de entregarla a los clientes.</Alerta>
      </Seccion>

      <Seccion numero={20} titulo="Cobrar facturas a crédito (recibos)">
        <p>Menú <b>Cobranzas → Cobrar</b> (o el botón <b>Cobrar</b> en la ficha de una factura a crédito). Busque al titular: aparecen sus facturas a crédito con saldo, la vencida más antigua primero.</p>
        <p>Escriba el <b>importe recibido</b>, la <b>forma de pago</b> y cuánto va a <b>cada factura</b>. El botón «Repartir: la más antigua primero» lo completa solo; si la institución eligió el reparto <b>automático</b> (Institución → Lecturas, facturación y cobros) se completa al escribir el importe. Siempre puede ajustarlo antes de confirmar.</p>
        <Maqueta>Recibe 50.000 · factura 001-001-0000004 (saldo 44.800) → 44.800 · factura 001-001-0000007 → 5.200 · recibo N° 0000012</Maqueta>
        <Tip>Se admiten <b>pagos parciales</b>: una factura puede recibir varios recibos, y un recibo puede pagar varias facturas.</Tip>
        <Alerta>El importe no puede superar la deuda: no se guarda saldo a favor, el vuelto se entrega en el momento. Si la conexión se corta mientras confirma, vuelva a pulsar: el sistema reconoce el mismo cobro y no lo duplica.</Alerta>
      </Seccion>

      <Seccion numero={21} titulo="Recibos e historial de cobros">
        <p><b>Cobranzas → Recibos</b>: cada recibo con su número, cliente, facturas, forma de pago e importe. En la ficha: <b>Imprimir (PDF)</b> con el importe en letras y el saldo que le queda al cliente.</p>
        <p><b>Anular</b> un recibo (con motivo) no lo borra: queda anulado con su número, el pago queda <b>revertido</b> y las facturas recuperan su saldo.</p>
        <p><b>Cobranzas → Historial de cobros</b>: todos los pagos del período (contado y recibos), con quién cobró y el total por forma de pago. Los revertidos siguen visibles con su motivo.</p>
        <Alerta>El recibo no reemplaza a la factura: es el comprobante del pago de facturas a crédito.</Alerta>
      </Seccion>

      <Seccion numero={22} titulo="Formas de pago">
        <p><b>Cobranzas → Formas de pago</b>: vienen cargadas Efectivo, Transferencia y POS. Puede agregar otras (ej. giros), pedir la referencia de la operación y desactivar las que no use (no se borran).</p>
        <Tip>Cada forma tiene un <b>tipo</b> (efectivo, transferencia, POS u otro): la caja muestra saldos separados por forma de pago, sin sumar transferencias como si fueran dinero en la caja.</Tip>
      </Seccion>

      <Seccion numero={23} titulo="Mi caja: abrir, cobrar y cerrar">
        <p>Para cobrar (factura contado o recibo) hace falta tener <b>su caja abierta</b>. Menú <b>Caja y gastos → Mi caja</b>: elija una caja libre, escriba el efectivo inicial (el cambio) y pulse <b>Abrir mi caja</b>. Cada cajero tiene su propia sesión.</p>
        <p>Todo lo que cobra o paga entra solo a su caja: no se cargan ingresos a mano. La pantalla muestra, por cada forma de pago, lo que entró, lo que salió y lo <b>esperado</b>.</p>
        <p>Al terminar, <b>Cerrar caja</b>: cuente y escriba lo que tiene en cada forma de pago. Si coincide, la caja queda <b>cerrada</b>; si no, queda <b>en revisión</b> y debe explicar la diferencia.</p>
        <Maqueta>Efectivo: inicial 100.000 + cobros 344.800 − gastos 15.000 = esperado 429.800 · contado 429.000 → diferencia −800 (en revisión)</Maqueta>
        <Alerta>Una caja cerrada no se modifica. Si después se anula un recibo o un gasto de esa caja, la devolución se registra en la caja ABIERTA de quien anula, con referencia al movimiento original.</Alerta>
      </Seccion>

      <Seccion numero={24} titulo="Sesiones de caja y revisión">
        <p><b>Caja y gastos → Sesiones de caja</b>: aperturas y cierres con su diferencia. El cajero ve las suyas; el supervisor (permiso «Ver todas las cajas…») ve todas.</p>
        <p>Una sesión <b>en revisión</b> la cierra el supervisor escribiendo el resultado (ej. «se descontó al cajero»). El <b>arqueo</b> en PDF trae los saldos por forma de pago, lo contado, la diferencia y todos los movimientos, con lugar para las firmas.</p>
        <Tip>Las cajas (ventanillas) se administran en <b>Caja y gastos → Cajas</b>. Viene cargada «CAJA1 · Caja principal».</Tip>
      </Seccion>

      <Seccion numero={25} titulo="Gastos">
        <p><b>Caja y gastos → Gastos → Registrar gasto</b>: fecha, motivo, importe, categoría, forma de pago, beneficiario y responsable. Si tiene comprobante, cargue su número y <b>adjunte la foto o el PDF</b>.</p>
        <p>Si no hay comprobante, <b>Generar boleta interna</b>: se imprime con número propio, se hace firmar por el beneficiario y se sube la foto de la boleta firmada.</p>
        <p>Un gasto registrado <b>todavía no sale de la caja</b>. Quien tiene el permiso de confirmar pulsa <b>Confirmar (sale de mi caja)</b>: el egreso entra una sola vez a su caja abierta.</p>
        <Alerta>El módulo es referencial: no es contabilidad ni compras. La boleta interna es evidencia administrativa y no sustituye a un comprobante fiscal. Un gasto confirmado no se corrige: se anula (queda el ingreso que lo compensa) y se carga de nuevo.</Alerta>
      </Seccion>

      <Seccion numero={26} titulo="Inicio e informes">
        <p>El <b>Inicio</b> muestra los indicadores que su usuario puede ver: conexiones, lecturas del mes, lo facturado y lo cobrado del mes, lo que se debe y lo vencido, cajas con diferencias y gastos sin confirmar. Cada indicador dice qué cuenta y lleva a su detalle.</p>
        <p>Menú <b>Informes → Informes y exportaciones</b>: elija el informe a la izquierda, ajuste los filtros (fechas o períodos, zona, barrio, usuario, estado) y pulse <b>Consultar</b>. Con <b>Excel</b> o <b>CSV</b> descarga exactamente lo que ve.</p>
        <Tip>Cada informe explica arriba <b>qué cuenta</b>. Por ejemplo, «Facturas emitidas» es lo facturado y «Recaudación» es el dinero realmente cobrado: no son lo mismo.</Tip>
        <Alerta>Cada usuario ve solo los informes de los módulos que tiene permitidos. Las exportaciones quedan registradas en la auditoría.</Alerta>
      </Seccion>

      <Seccion numero={27} titulo="Integraciones (API)">
        <p>Para que otro sistema (ej. uno contable) consulte los datos de la institución, el administrador crea una credencial en <b>Administración → Integraciones (API)</b>: el nombre del sistema, qué puede consultar, cuántas solicitudes por minuto y, si quiere, un vencimiento.</p>
        <Alerta>La clave se muestra UNA sola vez: cópiela y entréguela al responsable del otro sistema por un medio seguro. Si se pierde o se filtra, <b>Revóquela</b> y cree otra.</Alerta>
        <p>Las credenciales son de <b>solo lectura</b>: no pueden cargar, modificar ni anular nada. Cada uso queda en el <b>Registro</b> de la credencial.</p>
      </Seccion>

      <Seccion numero={28} titulo="Portal de abonados (consulta por internet)">
        <p>Los usuarios del servicio pueden consultar su cuenta desde el celular o la computadora: en la pantalla de ingreso, <b>«Consulte su cuenta aquí»</b> (dirección <b>/portal</b>). Con una sola cuenta ven sus datos en <b>todas</b> las juntas o aguateras donde son clientes.</p>
        <p>Para activarlo en esta institución: menú <b>Institución</b> → marcar «Ofrecer el portal de abonados» → Guardar.</p>
        <p>La primera vez la persona pulsa <b>Activar</b>, escribe su número de documento (C.I., RUC, DNI…) y su correo, recibe un <b>PIN</b> por correo (vale 15 minutos y una sola vez), ingresa con él y elige su contraseña. Ve su deuda, facturas y recibos (PDF), pagos, lecturas con la foto del medidor y sus conexiones. Solo puede consultar, no cambiar nada.</p>
        <Alerta>El PIN solo se envía si ese correo está cargado en la <b>ficha del cliente</b> con ese documento, y la persona ve cada junta solo si en su ficha de esa junta figuran el mismo documento y el mismo correo. Si alguien no lo recibe o no ve una junta, verifique y corrija el correo y el documento en <b>Padrón → Clientes</b>.</Alerta>
        <Tip>Si se olvidó la contraseña, se usa el mismo botón <b>Activar / olvidé mi clave</b>. Tras 5 intentos fallidos la cuenta se bloquea 15 minutos.</Tip>
      </Seccion>
    </div>
  )
}
