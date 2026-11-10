# Producto: alcance y reutilización

## Decisiones aprobadas

1. Un **negocio** es el límite de datos. Los clientes pertenecen al negocio, no a un profesional.
2. Un negocio puede tener varios profesionales. Cada turno se asigna a uno.
3. Administración y recepción pueden crear, modificar y cancelar turnos de cualquier agenda de su negocio. Un profesional puede hacerlo en su propia agenda.
   Todos pueden consultar el directorio compartido y registrar clientes; editar o archivar fichas queda en administración/recepción. El historial visible para un profesional se limita a turnos de su agenda.
4. La ficha del cliente muestra su historial compartido dentro del negocio, incluidos turnos cancelados y reprogramados.
5. La duración predeterminada se puede aceptar o modificar al crear un turno. El intervalo real, no solo la hora de inicio, determina la disponibilidad.
6. Se prioriza desktop. Mobile no es criterio de salida de la primera etapa.
7. El proyecto anterior permanece intacto y se usa solo como referencia de lectura.

## Modelo objetivo inicial

`Negocio` contiene `Usuario`, `Profesional`, `Cliente` y `Turno`. `Usuario` representa la identidad de acceso y su rol en el negocio; `Profesional` representa una agenda y puede estar asociado a un usuario. `Turno` referencia cliente, profesional y negocio. La identidad del cliente no exige DNI para todos los rubros.

Las operaciones de agenda se autorizan en el servidor y se registran con el usuario que las realizó. Cancelar o reprogramar no debe borrar el historial. Una reprogramación debe ser atómica: si no puede confirmarse el nuevo intervalo, el turno anterior continúa vigente.

El esquema inicial está en `db/001_initial.sql`. Usa identificadores UUID, claves foráneas compuestas por negocio para impedir relaciones cruzadas y una restricción de exclusión PostgreSQL para impedir dos turnos activos solapados del mismo profesional. El intervalo se persiste como instantes con zona (`timestamptz`); la zona horaria del negocio determina cómo se presenta la agenda local.

`db/002_security.sql` agrega sesiones opacas y RLS a las tablas de negocio; `db/003_role_policies.sql` endurece lectura/escritura por rol y agenda. La API usa un usuario de base distinto del migrador, con permisos específicos por tabla, y establece usuario, negocio y rol autenticados por transacción. **Límite actual:** las rutas de clientes/turnos están escritas pero no verificadas contra PostgreSQL; falta alta segura de cuentas del equipo, endurecimiento operativo, límites de intentos de login y verificación de punta a punta. Toda ruta futura debe consumir la dependencia de negocio y validar su permiso concreto.

`db/004_staff_invites.sql` agrega invitaciones de un solo uso. La aceptación usa funciones `SECURITY DEFINER` propiedad de `turnos_invite_executor`, rol `NOLOGIN` con `BYPASSRLS` y permisos de tablas limitados a esa operación. El migrador debe tener privilegio para crear ese rol (en el entorno local lo hace `postgres`). No se concede a la API escritura directa en usuarios ni membresías. Las cuentas existentes solo pueden aceptar una invitación con sesión propia y email coincidente. La entrega del token todavía es manual; no hay correo de invitación ni verificación automática del destinatario.

Los recordatorios siguen siendo requisito aunque n8n/Telegram desaparezcan. Email es el único canal de esta etapa; WhatsApp queda fuera por ahora y el teléfono se conserva como dato de contacto. El worker SMTP usa una cola propia con reintentos y una cuenta de base separada. El envío es al menos una vez y falta verificación operativa de punta a punta.

## Reutilización selectiva del proyecto anterior

| Fuente anterior | Tratamiento | Motivo |
| --- | --- | --- |
| `backend/app/services/availability_service.py` | Reutilizar la regla de solapamiento; reescribir cálculo de candidatos | Hoy depende de `Profesional` y duración fija; un candidato puede terminar fuera de jornada. |
| `backend/app/models/turno.py` | Aprovechar la idea de inicio/fin y estados; rediseñar relaciones | El turno actual pertenece directamente a un profesional y contiene campos de integraciones. |
| `backend/app/models/paciente.py` y `paciente_service.py` | Reutilizar comportamiento de ficha e historial; cambiar alcance | Hoy cliente e historial están particionados por `profesional_id` y DNI es obligatorio. |
| `backend/app/services/turno_service.py` | Extraer reglas verificadas por tests, no copiar íntegro | Mezcla persistencia de turnos, Calendar, Telegram y reserva temporal. |
| `front-profesional/` | Reaprovechar patrones visuales y flujos de agenda tras separar dominio | Alta actual usa terminología y campos de paciente odontológico. |
| `n8n-workflows/`, servicios Telegram/Calendar | No trasladar | Los casos de uso pasan a la aplicación; no se conserva la superficie de credenciales. |

## Orden de implementación

1. Núcleo de intervalos y disponibilidad, con tests. **Código escrito; tests pendientes de ejecución.**
2. Persistencia y migraciones del nuevo modelo de negocio, membresías, profesionales, clientes y turnos. **Esquema, migrador y entorno local escritos; aplicación real pendiente de verificación.**
3. Autenticación web y autorización por rol y pertenencia al negocio. **Login, sesión, membresía y contexto escritos; permisos finos de agenda pendientes de los endpoints de turnos.**
4. API de clientes, agendas y turnos, con pruebas de aislamiento y concurrencia. **Primeras rutas e invitaciones de equipo escritas; falta verificación con PostgreSQL.**
5. Interfaz desktop para operación diaria. **Primera interfaz escrita; falta integrar y verificar invitaciones, edición y reprogramación.** Solo después, mobile.

No se migran datos automáticamente del proyecto anterior. Si se requiere importación, tendrá un proceso explícito y reversible.


## Ajustes derivados de la prueba manual

- La agenda diaria muestra únicamente turnos `programado`; cancelados, reprogramados y completados quedan en historiales.
- El administrador no acepta invitaciones desde la sesión del negocio; las invitaciones se gestionan desde un modal en Profesionales.
- Los profesionales pueden modificar su propia ficha operativa y sus horarios; administración puede gestionar cualquier agenda.
- El directorio de un profesional queda limitado a clientes con historial en su propia agenda.
- El perfil profesional admite apellido, especialidad, teléfono, WhatsApp y notas. WhatsApp es dato de contacto: no activa recordatorios.
- Desde el detalle de un cliente se puede crear un turno con ese cliente preseleccionado.
