-- Esquema inicial del producto nuevo. No es una migración de la tesis.
-- Aplicar con un usuario de migraciones, no con el usuario de la aplicación.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE negocio (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre text NOT NULL CHECK (length(btrim(nombre)) > 0),
    zona_horaria text NOT NULL DEFAULT 'America/Argentina/Buenos_Aires',
    recordatorio_predeterminado_minutos integer NOT NULL DEFAULT 1440
        CHECK (recordatorio_predeterminado_minutos BETWEEN 1 AND 43200),
    creado_en timestamptz NOT NULL DEFAULT now(),
    archivado_en timestamptz
);

CREATE TABLE usuario (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL,
    password_hash text NOT NULL,
    nombre text NOT NULL CHECK (length(btrim(nombre)) > 0),
    activo boolean NOT NULL DEFAULT true,
    creado_en timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_usuario_email_normalizado UNIQUE (email),
    CONSTRAINT ck_usuario_email_normalizado CHECK (email = lower(btrim(email)))
);

CREATE TABLE membresia (
    negocio_id uuid NOT NULL REFERENCES negocio(id) ON DELETE RESTRICT,
    usuario_id uuid NOT NULL REFERENCES usuario(id) ON DELETE RESTRICT,
    rol text NOT NULL CHECK (rol IN ('admin', 'recepcionista', 'profesional')),
    activo boolean NOT NULL DEFAULT true,
    creado_en timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (negocio_id, usuario_id)
);
CREATE INDEX ix_membresia_usuario ON membresia (usuario_id, negocio_id);

CREATE TABLE profesional (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    negocio_id uuid NOT NULL REFERENCES negocio(id) ON DELETE RESTRICT,
    usuario_id uuid,
    nombre text NOT NULL CHECK (length(btrim(nombre)) > 0),
    apellido text,
    especialidad text,
    telefono text,
    whatsapp text,
    notas text,
    creado_por_usuario_id uuid REFERENCES usuario(id) ON DELETE RESTRICT,
    duracion_predeterminada_minutos integer NOT NULL DEFAULT 30
        CHECK (duracion_predeterminada_minutos BETWEEN 1 AND 1439),
    activo boolean NOT NULL DEFAULT true,
    creado_en timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_profesional_negocio_id UNIQUE (negocio_id, id),
    CONSTRAINT uq_profesional_usuario_por_negocio UNIQUE (negocio_id, usuario_id),
    CONSTRAINT fk_profesional_membresia FOREIGN KEY (negocio_id, usuario_id)
        REFERENCES membresia (negocio_id, usuario_id) ON DELETE RESTRICT
);
CREATE INDEX ix_profesional_negocio_activo ON profesional (negocio_id, activo);

CREATE TABLE horario_profesional (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    negocio_id uuid NOT NULL,
    profesional_id uuid NOT NULL,
    dia_semana smallint NOT NULL CHECK (dia_semana BETWEEN 0 AND 6),
    hora_inicio time NOT NULL,
    hora_fin time NOT NULL,
    CONSTRAINT ck_horario_orden CHECK (hora_fin > hora_inicio),
    CONSTRAINT fk_horario_profesional FOREIGN KEY (negocio_id, profesional_id)
        REFERENCES profesional (negocio_id, id) ON DELETE RESTRICT
);
CREATE INDEX ix_horario_profesional_dia
    ON horario_profesional (negocio_id, profesional_id, dia_semana);

CREATE TABLE cliente (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    negocio_id uuid NOT NULL REFERENCES negocio(id) ON DELETE RESTRICT,
    nombre text NOT NULL CHECK (length(btrim(nombre)) > 0),
    telefono text,
    email text,
    documento text,
    notas text,
    creado_en timestamptz NOT NULL DEFAULT now(),
    archivado_en timestamptz,
    CONSTRAINT uq_cliente_negocio_id UNIQUE (negocio_id, id)
);
CREATE INDEX ix_cliente_negocio_nombre ON cliente (negocio_id, nombre);
CREATE INDEX ix_cliente_negocio_telefono ON cliente (negocio_id, telefono)
    WHERE telefono IS NOT NULL;

CREATE TABLE turno (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    negocio_id uuid NOT NULL REFERENCES negocio(id) ON DELETE RESTRICT,
    profesional_id uuid NOT NULL,
    cliente_id uuid NOT NULL,
    inicio timestamptz NOT NULL,
    fin timestamptz NOT NULL,
    estado text NOT NULL DEFAULT 'programado'
        CHECK (estado IN ('programado', 'completado', 'cancelado', 'reprogramado')),
    motivo text,
    recordatorio_minutos_antes integer CHECK (recordatorio_minutos_antes BETWEEN 1 AND 43200),
    recordatorio_email boolean NOT NULL DEFAULT false,
    creado_por_usuario_id uuid NOT NULL,
    creado_en timestamptz NOT NULL DEFAULT now(),
    actualizado_en timestamptz NOT NULL DEFAULT now(),
    reprogramado_desde_id uuid,
    CONSTRAINT ck_turno_intervalo CHECK (fin > inicio),
    CONSTRAINT uq_turno_negocio_id UNIQUE (negocio_id, id),
    CONSTRAINT fk_turno_profesional FOREIGN KEY (negocio_id, profesional_id)
        REFERENCES profesional (negocio_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_turno_cliente FOREIGN KEY (negocio_id, cliente_id)
        REFERENCES cliente (negocio_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_turno_creador FOREIGN KEY (negocio_id, creado_por_usuario_id)
        REFERENCES membresia (negocio_id, usuario_id) ON DELETE RESTRICT,
    CONSTRAINT fk_turno_reprogramado_desde FOREIGN KEY (negocio_id, reprogramado_desde_id)
        REFERENCES turno (negocio_id, id) ON DELETE RESTRICT,
    CONSTRAINT ex_turno_profesional_intervalo EXCLUDE USING gist (
        profesional_id WITH =,
        tstzrange(inicio, fin, '[)') WITH &&
    ) WHERE (estado IN ('programado', 'completado'))
);
CREATE INDEX ix_turno_negocio_profesional_inicio
    ON turno (negocio_id, profesional_id, inicio);
CREATE INDEX ix_turno_negocio_cliente_inicio
    ON turno (negocio_id, cliente_id, inicio DESC);
CREATE INDEX ix_turno_negocio_estado_inicio
    ON turno (negocio_id, estado, inicio);

CREATE TABLE evento_turno (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    negocio_id uuid NOT NULL,
    turno_id uuid NOT NULL,
    actor_usuario_id uuid NOT NULL,
    accion text NOT NULL CHECK (accion IN ('creado', 'modificado', 'cancelado', 'reprogramado', 'completado')),
    detalle jsonb NOT NULL DEFAULT '{}'::jsonb,
    ocurrido_en timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_evento_turno FOREIGN KEY (negocio_id, turno_id)
        REFERENCES turno (negocio_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_evento_actor FOREIGN KEY (negocio_id, actor_usuario_id)
        REFERENCES membresia (negocio_id, usuario_id) ON DELETE RESTRICT
);
CREATE INDEX ix_evento_turno_historial
    ON evento_turno (negocio_id, turno_id, ocurrido_en);
