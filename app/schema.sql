CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS negocios (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre TEXT NOT NULL,
  zona_horaria TEXT NOT NULL DEFAULT 'America/Guayaquil',
  waba_id TEXT,
  phone_number_id TEXT UNIQUE,
  access_token TEXT,
  notificaciones_activas BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS usuarios (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  negocio_id UUID NOT NULL REFERENCES negocios(id) ON DELETE CASCADE,
  telefono TEXT NOT NULL UNIQUE,
  nombre TEXT,
  rol TEXT NOT NULL CHECK (rol IN ('vendedor','dueño'))
);

CREATE TABLE IF NOT EXISTS ventas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  negocio_id UUID NOT NULL REFERENCES negocios(id) ON DELETE CASCADE,
  vendedor_id UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  fecha_venta TIMESTAMPTZ NOT NULL DEFAULT now(),
  monto NUMERIC,
  moneda VARCHAR(8),
  cliente_nombre VARCHAR(255),
  pagador_nombre VARCHAR(255),
  productos_descripcion TEXT,
  metodo_pago VARCHAR(50),
  referencia_pago VARCHAR(255),
  estado VARCHAR(30) NOT NULL DEFAULT 'borrador'
    CHECK (estado IN ('borrador','confirmado','requiere_revision')),
  source_message_id VARCHAR(255) UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Evita duplicados lógicos por comprobante reenviado
CREATE UNIQUE INDEX IF NOT EXISTS uq_venta_comprobante
  ON ventas (negocio_id, metodo_pago, referencia_pago)
  WHERE referencia_pago IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_ventas_borrador
  ON ventas (vendedor_id, estado, updated_at);
