-- Defensa en profundidad: las rutas autorizan por rol y la base también.
-- El migrador ejecuta este archivo antes de conceder permisos al rol runtime.
DROP POLICY IF EXISTS profesional_lectura ON profesional; DROP POLICY IF EXISTS profesional_creacion ON profesional; DROP POLICY IF EXISTS profesional_cambio ON profesional;
CREATE POLICY profesional_lectura ON profesional FOR SELECT USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND (
        current_setting('app.rol', true) IN ('admin', 'recepcionista')
        OR usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
    )
);
CREATE POLICY profesional_creacion ON profesional FOR INSERT WITH CHECK (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND current_setting('app.rol', true) = 'admin'
);
CREATE POLICY profesional_cambio ON profesional FOR UPDATE USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND (
        current_setting('app.rol', true) = 'admin'
        OR (
            current_setting('app.rol', true) = 'profesional'
            AND usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
        )
    )
) WITH CHECK (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND (
        current_setting('app.rol', true) = 'admin'
        OR (
            current_setting('app.rol', true) = 'profesional'
            AND usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
        )
    )
);

DROP POLICY IF EXISTS horario_lectura ON horario_profesional; DROP POLICY IF EXISTS horario_creacion ON horario_profesional; DROP POLICY IF EXISTS horario_cambio ON horario_profesional; DROP POLICY IF EXISTS horario_borrado ON horario_profesional;
CREATE POLICY horario_lectura ON horario_profesional FOR SELECT USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND (
        current_setting('app.rol', true) IN ('admin', 'recepcionista')
        OR EXISTS (
            SELECT 1 FROM profesional p
            WHERE p.negocio_id = horario_profesional.negocio_id
              AND p.id = horario_profesional.profesional_id
              AND p.usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
              AND p.activo
        )
    )
);
CREATE POLICY horario_creacion ON horario_profesional FOR INSERT WITH CHECK (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND (
        current_setting('app.rol', true) = 'admin'
        OR (
            current_setting('app.rol', true) = 'profesional'
            AND EXISTS (
                SELECT 1 FROM profesional p
                WHERE p.negocio_id = horario_profesional.negocio_id
                  AND p.id = horario_profesional.profesional_id
                  AND p.usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
                  AND p.activo
            )
        )
    )
);
CREATE POLICY horario_cambio ON horario_profesional FOR UPDATE USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND (
        current_setting('app.rol', true) = 'admin'
        OR EXISTS (
            SELECT 1 FROM profesional p
            WHERE p.negocio_id = horario_profesional.negocio_id
              AND p.id = horario_profesional.profesional_id
              AND p.usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
              AND p.activo
        )
    )
) WITH CHECK (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND (
        current_setting('app.rol', true) = 'admin'
        OR EXISTS (
            SELECT 1 FROM profesional p
            WHERE p.negocio_id = horario_profesional.negocio_id
              AND p.id = horario_profesional.profesional_id
              AND p.usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
              AND p.activo
        )
    )
);
CREATE POLICY horario_borrado ON horario_profesional FOR DELETE USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND (
        current_setting('app.rol', true) = 'admin'
        OR EXISTS (
            SELECT 1 FROM profesional p
            WHERE p.negocio_id = horario_profesional.negocio_id
              AND p.id = horario_profesional.profesional_id
              AND p.usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
              AND p.activo
        )
    )
);

DROP POLICY IF EXISTS cliente_lectura ON cliente; DROP POLICY IF EXISTS cliente_creacion ON cliente; DROP POLICY IF EXISTS cliente_cambio ON cliente;
CREATE POLICY cliente_lectura ON cliente FOR SELECT USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND (
        current_setting('app.rol', true) IN ('admin', 'recepcionista')
        OR (
            current_setting('app.rol', true) = 'profesional'
            AND EXISTS (
                SELECT 1 FROM turno t
                JOIN profesional p
                  ON p.negocio_id = t.negocio_id AND p.id = t.profesional_id
                WHERE t.negocio_id = cliente.negocio_id
                  AND t.cliente_id = cliente.id
                  AND p.usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
            )
        )
    )
);
CREATE POLICY cliente_creacion ON cliente FOR INSERT WITH CHECK (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND current_setting('app.rol', true) IN ('admin', 'recepcionista', 'profesional')
);
CREATE POLICY cliente_cambio ON cliente FOR UPDATE USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND current_setting('app.rol', true) IN ('admin', 'recepcionista')
) WITH CHECK (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND current_setting('app.rol', true) IN ('admin', 'recepcionista')
);

DROP POLICY IF EXISTS turno_lectura ON turno; DROP POLICY IF EXISTS turno_creacion ON turno; DROP POLICY IF EXISTS turno_cambio ON turno;
CREATE POLICY turno_lectura ON turno FOR SELECT USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND (
        current_setting('app.rol', true) IN ('admin', 'recepcionista')
        OR EXISTS (
            SELECT 1 FROM profesional p
            WHERE p.negocio_id = turno.negocio_id
              AND p.id = turno.profesional_id
              AND p.usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
              AND p.activo
        )
    )
);
CREATE POLICY turno_creacion ON turno FOR INSERT WITH CHECK (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND (
        current_setting('app.rol', true) IN ('admin', 'recepcionista')
        OR EXISTS (
            SELECT 1 FROM profesional p
            WHERE p.negocio_id = turno.negocio_id
              AND p.id = turno.profesional_id
              AND p.usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
              AND p.activo
        )
    )
);
CREATE POLICY turno_cambio ON turno FOR UPDATE USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND (
        current_setting('app.rol', true) IN ('admin', 'recepcionista')
        OR EXISTS (
            SELECT 1 FROM profesional p
            WHERE p.negocio_id = turno.negocio_id
              AND p.id = turno.profesional_id
              AND p.usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
              AND p.activo
        )
    )
) WITH CHECK (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND (
        current_setting('app.rol', true) IN ('admin', 'recepcionista')
        OR EXISTS (
            SELECT 1 FROM profesional p
            WHERE p.negocio_id = turno.negocio_id
              AND p.id = turno.profesional_id
              AND p.usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
              AND p.activo
        )
    )
);

DROP POLICY IF EXISTS evento_lectura ON evento_turno; DROP POLICY IF EXISTS evento_creacion ON evento_turno;
CREATE POLICY evento_lectura ON evento_turno FOR SELECT USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND current_setting('app.rol', true) IN ('admin', 'recepcionista', 'profesional')
);
CREATE POLICY evento_creacion ON evento_turno FOR INSERT WITH CHECK (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND actor_usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
    AND current_setting('app.rol', true) IN ('admin', 'recepcionista', 'profesional')
);

