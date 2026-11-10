-- Límites compartidos entre procesos: no dependen de la memoria de Uvicorn.
CREATE TABLE security_rate_limit (
    bucket bytea PRIMARY KEY,
    window_started timestamptz NOT NULL,
    attempts integer NOT NULL CHECK (attempts > 0)
);
REVOKE ALL ON security_rate_limit FROM PUBLIC;

CREATE FUNCTION consumir_limite_seguridad(
    p_bucket bytea, p_max_attempts integer, p_window_seconds integer
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_allowed boolean;
BEGIN
    IF length(p_bucket) <> 32 OR p_max_attempts NOT BETWEEN 1 AND 1000
       OR p_window_seconds NOT BETWEEN 1 AND 86400 THEN
        RAISE EXCEPTION 'Parámetros de límite inválidos' USING ERRCODE = '22023';
    END IF;
    IF random() < 0.01 THEN
        DELETE FROM security_rate_limit
        WHERE bucket IN (
            SELECT bucket FROM security_rate_limit
            WHERE window_started < now() - interval '1 day' LIMIT 100
        );
    END IF;
    INSERT INTO security_rate_limit AS r (bucket, window_started, attempts)
    VALUES (p_bucket, now(), 1)
    ON CONFLICT (bucket) DO UPDATE
      SET window_started = CASE
            WHEN r.window_started <= now() - make_interval(secs => p_window_seconds)
            THEN now() ELSE r.window_started END,
          attempts = CASE
            WHEN r.window_started <= now() - make_interval(secs => p_window_seconds)
            THEN 1 ELSE r.attempts + 1 END
      WHERE r.window_started <= now() - make_interval(secs => p_window_seconds)
         OR r.attempts < p_max_attempts
    RETURNING true INTO v_allowed;
    RETURN COALESCE(v_allowed, false);
END;
$$;
REVOKE ALL ON FUNCTION consumir_limite_seguridad(bytea, integer, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION consumir_limite_seguridad(bytea, integer, integer) TO turnos_app;

-- La función de coincidencias no debe saltar el aislamiento del negocio activo
-- aunque el rol de la aplicación la invoque directamente.
CREATE OR REPLACE FUNCTION detectar_coincidencias_cliente(
    p_negocio_id uuid, p_email text, p_telefono text, p_documento text
)
RETURNS TABLE (id uuid, nombre text, telefono text, email text, documento text)
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT c.id, c.nombre, c.telefono, c.email, c.documento
    FROM cliente c
    WHERE p_negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
      AND current_setting('app.rol', true) IN ('admin', 'recepcionista', 'profesional')
      AND c.negocio_id = p_negocio_id
      AND c.archivado_en IS NULL
      AND (
        (NULLIF(btrim(p_email), '') IS NOT NULL AND lower(btrim(c.email)) = lower(btrim(p_email)))
        OR (
          length(regexp_replace(COALESCE(p_telefono, ''), '[^0-9]', '', 'g')) >= 10
          AND right(regexp_replace(COALESCE(c.telefono, ''), '[^0-9]', '', 'g'), 10)
            = right(regexp_replace(p_telefono, '[^0-9]', '', 'g'), 10)
        )
        OR (NULLIF(btrim(p_documento), '') IS NOT NULL AND lower(btrim(c.documento)) = lower(btrim(p_documento)))
      )
    ORDER BY c.nombre, c.id LIMIT 10;
$$;
REVOKE ALL ON FUNCTION detectar_coincidencias_cliente(uuid, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION detectar_coincidencias_cliente(uuid, text, text, text) TO turnos_app;
