-- Invitaciones de un solo uso. La aceptación se encapsula en una función
-- SECURITY DEFINER: el rol web no recibe INSERT directo en usuario/membresia.
CREATE TABLE invitacion_personal (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    negocio_id uuid NOT NULL REFERENCES negocio(id) ON DELETE RESTRICT,
    email text NOT NULL CHECK (email = lower(btrim(email))),
    rol text NOT NULL CHECK (rol IN ('recepcionista', 'profesional')),
    token_hash bytea NOT NULL UNIQUE,
    creado_por_usuario_id uuid NOT NULL,
    creado_en timestamptz NOT NULL DEFAULT now(),
    expira_en timestamptz NOT NULL,
    usado_en timestamptz,
    revocado_en timestamptz,
    CHECK (expira_en > creado_en),
    FOREIGN KEY (negocio_id, creado_por_usuario_id)
        REFERENCES membresia (negocio_id, usuario_id) ON DELETE RESTRICT
);
CREATE INDEX ix_invitacion_personal_negocio ON invitacion_personal (negocio_id, creado_en DESC);
ALTER TABLE invitacion_personal ENABLE ROW LEVEL SECURITY;
ALTER TABLE invitacion_personal FORCE ROW LEVEL SECURITY;
CREATE POLICY invitacion_admin ON invitacion_personal FOR ALL
    USING (negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
        AND current_setting('app.rol', true) = 'admin')
    WITH CHECK (negocio_id = nullif(current_setting('app.negocio_id', true), '')::uuid
        AND creado_por_usuario_id = nullif(current_setting('app.usuario_id', true), '')::uuid
        AND current_setting('app.rol', true) = 'admin');

-- Prevalidación barata para no calcular Argon2 por cada token arbitrario.
-- No reemplaza el bloqueo y la revalidación transaccional de aceptación.
CREATE FUNCTION validar_invitacion_personal(p_token_hash bytea, p_email text)
RETURNS boolean
LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
    SELECT EXISTS (
        SELECT 1 FROM invitacion_personal i
        JOIN negocio n ON n.id = i.negocio_id
        WHERE i.token_hash = p_token_hash AND i.email = p_email
          AND i.usado_en IS NULL AND i.revocado_en IS NULL
          AND i.expira_en > now() AND n.archivado_en IS NULL
    );
$$;
REVOKE ALL ON FUNCTION validar_invitacion_personal(bytea, text) FROM PUBLIC;

-- El migrador cambia el propietario a turnos_invite_executor (NOLOGIN,
-- BYPASSRLS), con permisos de tabla limitados a esta operación.
-- Usuarios ya existentes NO se vinculan por invitación pública: necesitan una
-- prueba de control adicional mediante sesión autenticada, aún no implementada.
CREATE FUNCTION aceptar_invitacion_personal(
    p_token_hash bytea, p_email text, p_nombre text, p_password_hash text
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_inv invitacion_personal%ROWTYPE;
    v_user_id uuid;
BEGIN
    SELECT * INTO v_inv FROM invitacion_personal
    WHERE token_hash = p_token_hash FOR UPDATE;
    IF NOT FOUND OR v_inv.usado_en IS NOT NULL OR v_inv.revocado_en IS NOT NULL
       OR v_inv.expira_en <= now() OR v_inv.email <> p_email
       OR NOT EXISTS (SELECT 1 FROM negocio WHERE id = v_inv.negocio_id AND archivado_en IS NULL)
    THEN
        RAISE EXCEPTION 'Invitación inválida o vencida' USING ERRCODE = 'P0001';
    END IF;
    IF EXISTS (SELECT 1 FROM usuario WHERE email = p_email) THEN
        RAISE EXCEPTION 'La cuenta ya existe; ingresá con tu usuario' USING ERRCODE = 'P0002';
    END IF;
    INSERT INTO usuario (email, nombre, password_hash)
    VALUES (p_email, p_nombre, p_password_hash) RETURNING id INTO v_user_id;
    INSERT INTO membresia (negocio_id, usuario_id, rol)
    VALUES (v_inv.negocio_id, v_user_id, v_inv.rol);
    IF v_inv.rol = 'profesional' THEN
        INSERT INTO profesional (negocio_id, usuario_id, nombre)
        VALUES (v_inv.negocio_id, v_user_id, p_nombre);
    END IF;
    UPDATE invitacion_personal SET usado_en = now() WHERE id = v_inv.id;
    RETURN v_user_id;
END;
$$;
REVOKE ALL ON FUNCTION aceptar_invitacion_personal(bytea, text, text, text) FROM PUBLIC;

-- Vincular cuenta preexistente sólo con sesión autenticada de ese usuario.
CREATE FUNCTION aceptar_invitacion_personal_existente(p_token_hash bytea)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
AS $$
DECLARE
    v_inv invitacion_personal%ROWTYPE;
    v_user usuario%ROWTYPE;
    v_usuario_id uuid;
BEGIN
    v_usuario_id := nullif(current_setting('app.usuario_id', true), '')::uuid;
    IF v_usuario_id IS NULL THEN
        RAISE EXCEPTION 'Sesión requerida' USING ERRCODE = 'P0003';
    END IF;
    SELECT * INTO v_inv FROM invitacion_personal
    WHERE token_hash = p_token_hash FOR UPDATE;
    IF NOT FOUND OR v_inv.usado_en IS NOT NULL OR v_inv.revocado_en IS NOT NULL
       OR v_inv.expira_en <= now()
       OR NOT EXISTS (SELECT 1 FROM negocio WHERE id = v_inv.negocio_id AND archivado_en IS NULL)
    THEN
        RAISE EXCEPTION 'Invitación inválida o vencida' USING ERRCODE = 'P0001';
    END IF;
    SELECT * INTO v_user FROM usuario WHERE id = v_usuario_id AND activo;
    IF NOT FOUND OR v_user.email <> v_inv.email THEN
        RAISE EXCEPTION 'Invitación no corresponde a esta cuenta' USING ERRCODE = 'P0001';
    END IF;
    IF EXISTS (SELECT 1 FROM membresia
               WHERE negocio_id = v_inv.negocio_id AND usuario_id = v_usuario_id) THEN
        RAISE EXCEPTION 'La membresía ya existe' USING ERRCODE = 'P0002';
    END IF;
    INSERT INTO membresia (negocio_id, usuario_id, rol)
    VALUES (v_inv.negocio_id, v_usuario_id, v_inv.rol);
    IF v_inv.rol = 'profesional' THEN
        INSERT INTO profesional (negocio_id, usuario_id, nombre)
        VALUES (v_inv.negocio_id, v_usuario_id, v_user.nombre);
    END IF;
    UPDATE invitacion_personal SET usado_en = now() WHERE id = v_inv.id;
    RETURN v_inv.negocio_id;
END;
$$;
REVOKE ALL ON FUNCTION aceptar_invitacion_personal_existente(bytea) FROM PUBLIC;
