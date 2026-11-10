-- Entregas por email: un intento lógico por turno. El worker escanea turnos
-- vigentes y calcula el vencimiento con la configuración actual del negocio.
CREATE TABLE recordatorio_email_entrega (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    turno_id uuid NOT NULL UNIQUE REFERENCES turno(id) ON DELETE RESTRICT,
    estado text NOT NULL DEFAULT 'pendiente'
        CHECK (estado IN ('pendiente', 'enviado', 'omitido')),
    intentos integer NOT NULL DEFAULT 0 CHECK (intentos >= 0),
    proximo_intento_en timestamptz NOT NULL DEFAULT now(),
    enviado_en timestamptz,
    ultimo_error text,
    creado_en timestamptz NOT NULL DEFAULT now(),
    actualizado_en timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_recordatorio_email_enviado
        CHECK ((estado = 'enviado') = (enviado_en IS NOT NULL))
);
CREATE INDEX ix_recordatorio_email_pendiente
    ON recordatorio_email_entrega (proximo_intento_en, id)
    WHERE estado = 'pendiente';

-- El rol de la app no accede a esta tabla. El worker usa un rol dedicado con
-- BYPASSRLS y privilegios explícitos otorgados en turnos/migrate.py.
ALTER TABLE recordatorio_email_entrega ENABLE ROW LEVEL SECURITY;
ALTER TABLE recordatorio_email_entrega FORCE ROW LEVEL SECURITY;
