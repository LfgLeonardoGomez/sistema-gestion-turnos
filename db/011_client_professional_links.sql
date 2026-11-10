CREATE TABLE cliente_profesional (
    negocio_id uuid NOT NULL,
    cliente_id uuid NOT NULL,
    profesional_id uuid NOT NULL,
    creado_por_usuario_id uuid NOT NULL REFERENCES usuario(id) ON DELETE RESTRICT,
    creado_en timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (negocio_id, cliente_id, profesional_id),
    FOREIGN KEY (negocio_id, cliente_id) REFERENCES cliente (negocio_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (negocio_id, profesional_id) REFERENCES profesional (negocio_id, id) ON DELETE RESTRICT
);
ALTER TABLE cliente_profesional ENABLE ROW LEVEL SECURITY;
CREATE POLICY cliente_profesional_negocio ON cliente_profesional USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
);
GRANT SELECT, INSERT ON cliente_profesional TO turnos_app;

DROP POLICY IF EXISTS cliente_lectura ON cliente;
CREATE POLICY cliente_lectura ON cliente FOR SELECT USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND (
        current_setting('app.rol', true) IN ('admin', 'recepcionista')
        OR creado_por_usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
        OR EXISTS (
            SELECT 1 FROM cliente_profesional cp JOIN profesional cp_p
              ON cp_p.negocio_id = cp.negocio_id AND cp_p.id = cp.profesional_id
            WHERE cp.negocio_id = cliente.negocio_id AND cp.cliente_id = cliente.id
              AND cp_p.usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
        )
        OR EXISTS (
            SELECT 1 FROM turno t JOIN profesional p
              ON p.negocio_id = t.negocio_id AND p.id = t.profesional_id
            WHERE t.negocio_id = cliente.negocio_id AND t.cliente_id = cliente.id
              AND p.usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
        )
    )
);
