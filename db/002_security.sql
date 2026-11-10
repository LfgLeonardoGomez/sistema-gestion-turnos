-- Sesiones opacas: solo se persiste el hash del token de cookie.
CREATE TABLE sesion (
    token_hash bytea PRIMARY KEY,
    usuario_id uuid NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    creado_en timestamptz NOT NULL DEFAULT now(),
    expira_en timestamptz NOT NULL,
    revocado_en timestamptz,
    CONSTRAINT ck_sesion_expiracion CHECK (expira_en > creado_en)
);
CREATE INDEX ix_sesion_usuario ON sesion (usuario_id, expira_en);

-- La identidad y el negocio se establecen con set_config(..., true) por
-- transacción. Sin contexto, estas políticas no devuelven filas.
ALTER TABLE negocio ENABLE ROW LEVEL SECURITY;
ALTER TABLE negocio FORCE ROW LEVEL SECURITY;
CREATE POLICY negocio_lectura ON negocio FOR SELECT USING (
    id IN (
        SELECT m.negocio_id FROM membresia AS m
        WHERE m.usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
          AND m.activo
    )
);

ALTER TABLE membresia ENABLE ROW LEVEL SECURITY;
ALTER TABLE membresia FORCE ROW LEVEL SECURITY;
CREATE POLICY membresia_lectura ON membresia FOR SELECT USING (
    (usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid OR
     negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid)
    AND activo
);

ALTER TABLE profesional ENABLE ROW LEVEL SECURITY;
ALTER TABLE profesional FORCE ROW LEVEL SECURITY;
CREATE POLICY profesional_negocio ON profesional FOR ALL USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
) WITH CHECK (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
);

ALTER TABLE horario_profesional ENABLE ROW LEVEL SECURITY;
ALTER TABLE horario_profesional FORCE ROW LEVEL SECURITY;
CREATE POLICY horario_negocio ON horario_profesional FOR ALL USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
) WITH CHECK (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
);

ALTER TABLE cliente ENABLE ROW LEVEL SECURITY;
ALTER TABLE cliente FORCE ROW LEVEL SECURITY;
CREATE POLICY cliente_negocio ON cliente FOR ALL USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
) WITH CHECK (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
);

ALTER TABLE turno ENABLE ROW LEVEL SECURITY;
ALTER TABLE turno FORCE ROW LEVEL SECURITY;
CREATE POLICY turno_negocio ON turno FOR ALL USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
) WITH CHECK (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
);

ALTER TABLE evento_turno ENABLE ROW LEVEL SECURITY;
ALTER TABLE evento_turno FORCE ROW LEVEL SECURITY;
CREATE POLICY evento_negocio ON evento_turno FOR ALL USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
) WITH CHECK (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
);
