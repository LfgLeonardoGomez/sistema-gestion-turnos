CREATE OR REPLACE FUNCTION detectar_coincidencias_cliente(
    p_negocio_id uuid,
    p_email text,
    p_telefono text,
    p_documento text
)
RETURNS TABLE (id uuid, nombre text, telefono text, email text, documento text)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT c.id, c.nombre, c.telefono, c.email, c.documento
    FROM cliente c
    WHERE c.negocio_id = p_negocio_id
      AND c.archivado_en IS NULL
      AND (
        (NULLIF(btrim(p_email), '') IS NOT NULL AND lower(btrim(c.email)) = lower(btrim(p_email)))
        OR (NULLIF(regexp_replace(COALESCE(p_telefono, ''), '[^0-9]', '', 'g'), '') IS NOT NULL
            AND regexp_replace(COALESCE(c.telefono, ''), '[^0-9]', '', 'g') = regexp_replace(p_telefono, '[^0-9]', '', 'g'))
        OR (NULLIF(btrim(p_documento), '') IS NOT NULL AND lower(btrim(c.documento)) = lower(btrim(p_documento)))
      )
    ORDER BY c.nombre, c.id
    LIMIT 10;
$$;

GRANT EXECUTE ON FUNCTION detectar_coincidencias_cliente(uuid, text, text, text) TO turnos_app;
