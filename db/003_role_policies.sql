-- Defensa en profundidad: las rutas autorizan por rol y la base también.
-- El migrador ejecuta este archivo antes de conceder permisos al rol runtime.
DROP POLICY profesional_negocio ON profesional;
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

DROP POLICY horario_negocio ON horario_profesional;
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

DROP POLICY cliente_negocio ON cliente;
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

DROP POLICY turno_negocio ON turno;
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

DROP POLICY evento_negocio ON evento_turno;
CREATE POLICY evento_lectura ON evento_turno FOR SELECT USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND current_setting('app.rol', true) IN ('admin', 'recepcionista', 'profesional')
);
CREATE POLICY evento_creacion ON evento_turno FOR INSERT WITH CHECK (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND actor_usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
    AND current_setting('app.rol', true) IN ('admin', 'recepcionista', 'profesional')
);
