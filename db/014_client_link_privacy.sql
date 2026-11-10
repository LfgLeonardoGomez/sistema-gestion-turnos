-- Las coincidencias deben respetar exactamente la visibilidad del invocador.
-- SECURITY DEFINER exponía fichas ajenas a la agenda profesional.
ALTER FUNCTION detectar_coincidencias_cliente(uuid, text, text, text) SECURITY INVOKER;

-- La tabla de vínculos tampoco debe permitir insertar relaciones arbitrarias
-- mediante el rol SQL de runtime, aun si se saltea la ruta HTTP.
ALTER TABLE cliente_profesional FORCE ROW LEVEL SECURITY;
DROP POLICY cliente_profesional_negocio ON cliente_profesional;
CREATE POLICY cliente_profesional_lectura ON cliente_profesional FOR SELECT USING (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
);
CREATE POLICY cliente_profesional_creacion ON cliente_profesional FOR INSERT WITH CHECK (
    negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
    AND creado_por_usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
    AND (
        current_setting('app.rol', true) IN ('admin', 'recepcionista')
        OR (
            current_setting('app.rol', true) = 'profesional'
            AND EXISTS (
                SELECT 1 FROM profesional p
                WHERE p.negocio_id = cliente_profesional.negocio_id
                  AND p.id = cliente_profesional.profesional_id
                  AND p.usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
                  AND p.activo
            )
            AND EXISTS (
                SELECT 1 FROM cliente c
                WHERE c.negocio_id = cliente_profesional.negocio_id
                  AND c.id = cliente_profesional.cliente_id
                  AND c.archivado_en IS NULL
            )
        )
    )
);
