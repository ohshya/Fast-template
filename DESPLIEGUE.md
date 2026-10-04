# Pendiente para el despliegue

Cosas que no se pueden hacer ni comprobar en la plantilla porque dependen del servidor, del dominio o del contenido del proyecto. Cómo se lanza la API y el proxy está en `GUIA.md`, sección 6; aquí solo lo que hay que acordarse de hacer.

## Servidor y red

- [ ] **Redirigir HTTP a HTTPS** en el proxy. La API ya envía HSTS y cookies `Secure` con `DEBUG=false`, pero la redirección la hace el proxy.
- [ ] **Certificado TLS** válido y renovación automática.
- [ ] **Comprimir** (gzip o brotli) los `.js`, `.css`, `.svg` y `.html` del frontend. Sin compresión la carga inicial pesa varias veces más.
- [ ] **Caché del frontend**: los archivos de `dist/assets/` llevan hash en el nombre, así que `Cache-Control: public, max-age=31536000, immutable`. `index.html` sin caché larga.
- [ ] **Devolver `index.html`** en las rutas del frontend (`/users`, `/roles`…).
- [ ] **Cabeceras de seguridad de las páginas** (`Content-Security-Policy`, `X-Frame-Options`, `Referrer-Policy`…). La API solo las pone en sus respuestas.
- [ ] **Límite de peticiones por IP** y límite del cuerpo (1 MiB) en el proxy.
- [ ] **`robots.txt` y `X-Robots-Tag`** si el panel no debe aparecer en buscadores (el caso de la plantilla): `Disallow: /` y `X-Robots-Tag: noindex`.
- [ ] **Copias de seguridad** de PostgreSQL y prueba de restauración.

## Contenido legal (depende del titular y del país)

- [ ] **Aviso legal**: titular, domicilio, contacto, registro.
- [ ] **Política de privacidad**. La plantilla guarda: usuario, rol, IP y navegador de cada sesión, y un registro de auditoría con quién hizo qué. Dilo en la política, con plazos de conservación.
- [ ] **Aviso de cookies**. La plantilla solo usa las cookies técnicas de la sesión (necesarias, `HttpOnly`): informar basta, no hace falta banner de consentimiento. Si añades analítica, publicidad o cualquier cookie no necesaria, sí hace falta.

## Solo si el proyecto es un sitio público

- [ ] Sitemap, `robots.txt` abierto y datos estructurados.
- [ ] Meta título y descripción propios de cada página pública, e imagen para compartir en redes.
- [ ] Ficha de Google Business.
- [ ] Analítica (con consentimiento previo) y una sola llamada a la acción por página.
- [ ] Botón de WhatsApp.
- [ ] Formularios públicos con antispam (CAPTCHA o similar, y limitación en el proxy).
- [ ] Imágenes comprimidas y con texto alternativo.
- [ ] Revisar enlaces rotos antes de publicar.
