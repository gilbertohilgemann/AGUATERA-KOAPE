/*
 * Service worker de Koape Aguateras (aplicación del cobrador).
 * Guarda la aplicación (HTML, JS, CSS, íconos) para poder ABRIRLA sin conexión. No guarda respuestas de la API
 * ni fotos: los datos del recorrido y las lecturas pendientes viven en IndexedDB (ver src/cobrador/almacenLocal.ts).
 * Solo funciona con https (o en la misma PC con localhost); por http en la red local el navegador no lo activa.
 */
const VERSION = 'koape-aguateras-v1'
const BASE = ['/', '/index.html', '/manifest.webmanifest', '/icono-192.png', '/icono-512.png', '/favicon.png']

self.addEventListener('install', (evento) => {
  evento.waitUntil(caches.open(VERSION).then((c) => c.addAll(BASE)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (evento) => {
  evento.waitUntil(
    caches.keys().then((claves) => Promise.all(claves.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (evento) => {
  const pedido = evento.request
  if (pedido.method !== 'GET') return
  const url = new URL(pedido.url)
  if (url.origin !== self.location.origin) return // API en otro puerto, fuentes, mosaicos del mapa
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/admin') || url.pathname.startsWith('/media/')) return

  // Páginas: primero la red (versión nueva); sin conexión, la aplicación guardada.
  if (pedido.mode === 'navigate') {
    evento.respondWith(
      fetch(pedido).then((r) => {
        // Solo una página buena reemplaza la guardada (no un error ni la página de un portal wifi).
        const html = (r.headers.get('content-type') || '').includes('text/html')
        if (r.ok && !r.redirected && html && r.url.startsWith(self.location.origin)) {
          const copia = r.clone()
          caches.open(VERSION).then((c) => c.put('/index.html', copia))
        }
        return r
      }).catch(() => caches.match('/index.html').then((r) => r || caches.match('/'))),
    )
    return
  }

  // Archivos de la aplicación (con nombre versionado por Vite): de la caché si están; si no, de la red y se guardan.
  evento.respondWith(
    caches.match(pedido).then((guardado) => guardado || fetch(pedido).then((r) => {
      if (r.ok && (url.pathname.startsWith('/assets/') || BASE.includes(url.pathname))) {
        const copia = r.clone()
        caches.open(VERSION).then((c) => c.put(pedido, copia))
      }
      return r
    })),
  )
})
