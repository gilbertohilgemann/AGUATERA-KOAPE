/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** «1» muestra en el ingreso los botones de acceso de la aguatera demo (frontend/.env). */
  readonly VITE_ACCESO_DEMO?: string
  /** URL completa de la API (solo si el backend está en otro host). */
  readonly VITE_API_URL?: string
  /** Puerto del backend; lo escribe el instalador en frontend/.env.local. */
  readonly VITE_API_PUERTO?: string
  /** En el servidor: la página y la API comparten dirección (el servidor web reenvía /api). */
  readonly VITE_API_MISMO_ORIGEN?: string
  /** Lo define Vite: verdadero en la versión compilada (`npm run build`). */
  readonly PROD: boolean
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
