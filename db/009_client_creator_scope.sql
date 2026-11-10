ALTER TABLE cliente
    ADD COLUMN IF NOT EXISTS creado_por_usuario_id uuid REFERENCES usuario(id) ON DELETE RESTRICT;

DROP POLICY IF EXISTS cliente_lectura ON cliente;
CREATE POLICY cliente_lectura ON cliente FOR SELECT USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND (
        current_setting('app.rol', true) IN ('admin', 'recepcionista')
        OR creado_por_usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
        OR EXISTS (
            SELECT 1 FROM turno t
            JOIN profesional p ON p.negocio_id = t.negocio_id AND p.id = t.profesional_id
            WHERE t.negocio_id = cliente.negocio_id
              AND t.cliente_id = cliente.id
              AND p.usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
        )
    )
);
