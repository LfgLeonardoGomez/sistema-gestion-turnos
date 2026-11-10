-- Perfil profesional ampliado. Los campos complementarios pueden completarse
-- luego de aceptar la invitación; nombre conserva compatibilidad con el esquema inicial.
ALTER TABLE profesional ADD COLUMN IF NOT EXISTS apellido text;
ALTER TABLE profesional ADD COLUMN IF NOT EXISTS especialidad text;
ALTER TABLE profesional ADD COLUMN IF NOT EXISTS telefono text;
ALTER TABLE profesional ADD COLUMN IF NOT EXISTS whatsapp text;
ALTER TABLE profesional ADD COLUMN IF NOT EXISTS notas text;

ALTER TABLE profesional DROP CONSTRAINT IF EXISTS ck_profesional_apellido;
ALTER TABLE profesional ADD CONSTRAINT ck_profesional_apellido
    CHECK (apellido IS NULL OR length(btrim(apellido)) > 0);
ALTER TABLE profesional DROP CONSTRAINT IF EXISTS ck_profesional_especialidad;
ALTER TABLE profesional ADD CONSTRAINT ck_profesional_especialidad
    CHECK (especialidad IS NULL OR length(btrim(especialidad)) > 0);
