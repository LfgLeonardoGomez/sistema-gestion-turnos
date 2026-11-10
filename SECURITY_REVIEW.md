# Revisión de seguridad — 2026-09-23

## Alcance y modelo

Se revisaron API FastAPI, frontend React, migraciones PostgreSQL/RLS, sesiones,
invitaciones, recordatorios y Compose. Se trata de un entorno de desarrollo local:
`frontend` es Vite y `api`/`frontend` se publican sólo en `127.0.0.1`.
**No es una certificación ni una prueba de penetración externa.**

## Corregido en esta revisión

| Riesgo | Cambio | Verificación |
|---|---|---|
| Fuerza bruta de login/invitaciones | Cupos atómicos en PostgreSQL por IP, cuenta, token o actor; HTTP 429 y Retry-After | Noveno intento de login de prueba devolvió 429 |
| Enumeración masiva de clientes | Cupo por usuario y negocio para coincidencias | Revisión de ruta y función |
| Función SECURITY DEFINER sin contexto | `detectar_coincidencias_cliente` exige negocio/rol de la transacción; EXECUTE revocado a PUBLIC | Invocación sin contexto como `turnos_app` devolvió 0; privilegio PUBLIC falso |
| Respuestas sensibles cacheables / framing | `Cache-Control: no-store`, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` | Cabeceras observadas en 401 |
| Despliegue accidental sin HTTPS | Configuración rechaza HTTP o cookie no segura fuera de localhost | Validación en `Settings` |
| Exposición de OpenAPI en producción | `/docs`, `/redoc`, `/openapi.json` sólo con `APP_ENV=development` | Entorno local mantiene `/docs` |
| Parámetros costosos o ilimitados | Contraseña de login <=1024, motivo <=2000, rango <=31 días, offset <=10000, año de calendario acotado | Revisión de validación |
| Cuerpo JSON excesivo | Middleware ASGI limita a 64 KiB antes del parseo, también con transferencia chunked | Ambos casos devolvieron 413; `/health` siguió en 200 |
| Migración inicial sin rol runtime | El migrador crea `turnos_app` antes de aplicar archivos que le conceden privilegios | Migraciones 001–013 aplicadas en base temporal vacía, luego eliminada |

## Controles existentes verificados

- No hay JWT. La autenticación usa token aleatorio opaco de 32 bytes, sólo su SHA-256
  en PostgreSQL, cookie `HttpOnly; SameSite=Strict`, expiración y revocación.
  En HTTPS la cookie usa el prefijo `__Host-`.
- Las consultas revisadas usan parámetros SQL; los fragmentos de SQL concatenados
  en clientes son constantes del servidor, no texto del usuario. Una búsqueda
  autenticada con `q=' OR 1=1 --` devolvió cero clientes, sin alterar la consulta.
- Cada ruta de negocio usa sesión, membresía activa y `X-Business-Id`; el contexto
  RLS se establece por transacción. Acciones de agenda comprueban propietario
  profesional; admin/recepción pueden gestionar turnos.
- Las invitaciones son de un solo uso, caducan a las 48 horas, almacenan hash del
  token y se aceptan mediante funciones transaccionales.
- React no usa `innerHTML`/`dangerouslySetInnerHTML` ni guarda tokens en Web Storage.
- Las escrituras requieren `Origin` exacto; la cookie Strict agrega defensa CSRF.
- Smoke real: admin y profesional iniciaron sesión (200), `GET /auth/me` respondió
  200, otro negocio devolvió 403 y un profesional no pudo emitir invitación (403).
- `npm audit --omit=dev --audit-level=moderate` en el lockfile actual informó
  cero vulnerabilidades; esto no cubre dependencias Python ni futuras versiones.

## Riesgos pendientes, por prioridad

1. **Alto — producción aún no preparada.** Compose ejecuta Vite y expone secretos
   como variables de entorno; faltan proxy TLS, gestión de secretos, política de
   `Host`/proxy confiable, límites de cuerpo y de conexiones a nivel de ingress,
   logs/auditoría de seguridad, rotación de credenciales y backups verificados.
   No publicar este Compose en Internet.
2. **Resuelto en migración 014 — coincidencia de clientes entre agendas.** La
   función de coincidencias ahora usa `SECURITY INVOKER`: un profesional sólo
   recibe fichas que RLS ya le permite leer. Administración/recepción puede
   compartir explícitamente una ficha con un profesional activo del mismo negocio.
   El intercambio es deliberadamente manual; puede haber duplicados cuando el
   profesional no ve una ficha preexistente. Aún falta definir conciliación de
   duplicados y, si se requiere autoservicio, un consentimiento verificable del cliente.
3. **Medio — límite de IP tras proxy.** Se usa la dirección del peer, NO se confía
   en `X-Forwarded-For`. En producción el proxy debe ser explícitamente confiable
   y aplicar también límites perimetrales; de otro modo muchos usuarios comparten
   un bucket IP. El cupo por cuenta sigue vigente.
4. **Medio — bloqueo temporal de cuenta.** Ocho intentos por cuenta/15 minutos
   frenan adivinación pero pueden causar denegación temporal deliberada. Para
   producción considerar MFA, demoras progresivas y alertas.
5. **Medio — autorización RLS depende de variables de sesión configurables por el
   rol de aplicación.** Un atacante con acceso directo a sus credenciales puede
   suplantar contexto; RLS es defensa frente a errores de consultas/rutas, no una
   barrera frente al robo de credenciales de PostgreSQL. Mantener DB inaccesible
   desde Internet y rotar secretos.
6. **Medio — límites por operación incompletos.** Hay un tope global de 64 KiB
   antes del parseo y cupos para los endpoints más sensibles, pero aún faltan
   límites perimetrales de conexiones/tiempo y cuotas para escrituras intensivas.
7. **Medio — dependencias Python no fijadas con lock/hash.** `pyproject.toml` usa
   rangos; definir lock reproducible y escaneo de vulnerabilidades antes del
   despliegue. Node usa `package-lock.json` y `npm ci`.
8. **Bajo/operativo — sesiones.** No hay MFA, recuperación de contraseña,
   administración de dispositivos ni revocación global; definir estos flujos
   antes de incorporar negocios reales.

## Pruebas todavía necesarias

- Ampliar la matriz HTTP a todas las rutas de escritura. Ya hay casos reales de
  401/403/404/200 para acceso a fichas entre roles y negocios, más pruebas SQL
  transaccionales de dos negocios, tres roles, coincidencias y vínculos.
- Las migraciones 001–014 pasaron desde una base temporal vacía. El test de
  concurrencia también crea una base temporal desde cero y la elimina.
- Ampliar pruebas de concurrencia a reprogramaciones y carreras de revocación
  contra aceptación. La emisión/aceptación única, el rate limit y la creación
  simultánea de turnos ya están cubiertos.
- DAST en un despliegue de staging con proxy HTTPS; revisión de CSP del frontend
  de producción y pruebas de timeout/slow clients.
