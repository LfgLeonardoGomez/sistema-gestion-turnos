# Sistema de gestión de turnos

Producto para negocios con varios profesionales y una agenda compartida. Este repositorio es **nuevo**: el proyecto anterior `Tesis-N8N-turnos` se consulta únicamente como fuente de ideas y código reutilizable; no se modifica ni se copia íntegramente.

## Alcance acordado

- Cada negocio tiene clientes persistentes y profesionales con agendas propias.
- Administración y recepción gestionan todas las agendas del negocio; cada profesional gestiona la suya.
- Los turnos conservan un historial por cliente, incluso si se cancelan o reprograman.
- Existe una duración predeterminada; al crear un turno se puede ajustar, siempre que el intervalo completo esté disponible.
- La primera interfaz será desktop. Mobile queda para una etapa posterior.
- n8n, Telegram y Google Calendar no forman parte del núcleo del producto. Sus flujos de negocio deben reemplazarse antes de retirar código heredado.

Ver [alcance y plan de reutilización](docs/producto.md).

## Estado

Primeras iteraciones: núcleo de agenda, esquema PostgreSQL, migrador, sesiones, rutas de clientes/profesionales/turnos, invitaciones de personal y una interfaz desktop. El stack local ya fue verificado con PostgreSQL, API y frontend; los recordatorios por email están implementados, pero todavía falta validar entrega contra un SMTP real antes de producción.

## Preparación local prevista

Requiere Docker Compose. Copiar `.env.example` a `.env` y cambiar las tres contraseñas (la clave de la app debe tener al menos 16 caracteres). El archivo `.env` está ignorado por Git. `compose.yaml` levanta PostgreSQL, aplica migraciones con la cuenta administradora y ejecuta la API con `turnos_app`, una cuenta distinta sin privilegios de migración. Las migraciones 001–014 se verificaron desde una base temporal vacía.

El comando local inicial es `docker compose up --build`; después de cambios de código o migraciones, usar `docker compose up -d --no-build` para respetar el flujo de desarrollo. PostgreSQL, migraciones, API y frontend Vite se levantan juntos. La UI queda en `http://localhost:5173` salvo que se configure `FRONTEND_PORT`; su proxy interno envía `/auth`, `/clientes`, `/profesionales`, `/turnos` y `/personal` al servicio `api`. `APP_ORIGIN` debe coincidir con el origen que uses en el navegador. El worker de email se activa aparte con `docker compose --profile reminders up`.

Para crear el primer negocio y administrador, completar temporalmente las cuatro variables `BOOTSTRAP_*` en `.env` y ejecutar `docker compose run --rm migrate python -m turnos.bootstrap`. Después, borrar la contraseña de bootstrap de `.env`.

Para cargar datos demo adicionales de forma idempotente (2 profesionales con perfiles y horarios, 4 clientes y un turno futuro por cliente), completar `SEED_BUSINESS_NAME` y `SEED_PROFESSIONAL_PASSWORD` en `.env` y ejecutar explícitamente:

```powershell
docker compose run --rm migrate python -m turnos.seed
```

El seed no crea negocios ni administradores: requiere que el bootstrap ya haya sido ejecutado. Las cuentas profesionales demo quedan con la contraseña indicada en `SEED_PROFESSIONAL_PASSWORD`.

La API expone `/health`, `/ready`, `/auth/login`, `/auth/logout`, `/auth/me`, `/auth/context`, `/clientes`, `/profesionales`, `/turnos` y `/personal/invitaciones`. Las operaciones de negocio requieren `X-Business-Id` y pertenencia activa al negocio. Las escrituras requieren `Origin` idéntico a `APP_ORIGIN`; la sesión usa cookie HttpOnly con `SameSite=Strict`. `COOKIE_SECURE=false` es **solo para localhost sin HTTPS**; en un despliegue real debe ser `true`, con TLS y origen correcto. No se habilita CORS entre dominios: la UI desktop se sirve desde el mismo origen mediante proxy en desarrollo.

La API aplica límites compartidos en PostgreSQL a login, invitaciones y búsqueda de coincidencias, además de rechazar cuerpos HTTP mayores a 64 KiB. `APP_ENV=development` se permite sólo en localhost y habilita Swagger; en producción se oculta la documentación interactiva. **Este Compose es sólo de desarrollo y no debe exponerse a Internet.** Ver [revisión de seguridad](SECURITY_REVIEW.md) para controles verificados y riesgos pendientes.

Las coincidencias de clientes respetan la visibilidad del usuario: un profesional no puede descubrir fichas de otras agendas probando un email, teléfono o documento. Si necesita reutilizar una ficha que todavía no ve, administración o recepción la busca en **Clientes** y usa **Compartir ficha con profesional**. La relación queda dentro del mismo negocio y permite que el profesional vea la ficha; la alternativa de crear otra ficha puede producir duplicados que habrá que conciliar manualmente.

El administrador puede emitir una invitación de 48 horas para recepción o un profesional. El token se muestra una vez para entrega manual; la base guarda solo su hash. La aceptación crea una cuenta nueva o, si la cuenta ya existe, exige iniciar sesión con ella antes de sumarla al negocio. **No hay correo de invitación ni verificación automática del destinatario todavía**: tratá el token como una credencial y no lo pongas en una URL pública.

Los recordatorios por email usan plazo predeterminado por negocio y override por turno. El worker `turnos.reminders` escanea turnos vigentes, envía por SMTP y registra estado/reintentos. Para activarlo, configurar `SMTP_HOST`, `SMTP_FROM` y, si hace falta autenticación, `SMTP_USER`/`SMTP_PASSWORD`; luego iniciar `docker compose --profile reminders up`. Sin ese perfil, seleccionar email no envía nada. La entrega es al menos una vez: una caída tras SMTP y antes del commit puede duplicar el mensaje. WhatsApp queda fuera por ahora; el teléfono del cliente sigue siendo contacto general.

La pantalla **Turnos** alterna entre agenda diaria y calendario mensual de turnos programados. El directorio de clientes tiene búsqueda por nombre, email, teléfono o documento. Los teléfonos nuevos o editados aceptan un móvil argentino con código de área (por ejemplo `261 209 4262`, `0261 15 209 4262` o `+54 9 261 209 4262`) y se guardan en formato `+549` seguido de diez dígitos nacionales. Otros países quedan fuera por ahora. Los teléfonos históricos se conservan como fueron cargados y deben revisarse antes de usarse para mensajería. En el perfil profesional, el indicador «Este teléfono también es mi WhatsApp» evita guardar dos números distintos.

La suite unitaria se ejecuta con `python -m unittest discover -s tests -v`. Para incluir pruebas de RLS, autorización HTTP y concurrencia con PostgreSQL real, sin build:

```powershell
docker compose run --rm --no-deps -e RUN_DB_INTEGRATION_TESTS=1 -v "${PWD}/tests:/app/tests:ro" migrate python -m unittest discover -s tests -v
```

Los casos RLS revierten sus datos con `ROLLBACK`; los de invitaciones/turnos crean y eliminan una base temporal propia. El test de rate limit limpia su bucket aleatorio al finalizar.


