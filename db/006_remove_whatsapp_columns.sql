-- Compatible con bases donde 001 se aplicó antes de posponer WhatsApp.
ALTER TABLE cliente DROP COLUMN IF EXISTS whatsapp_consentimiento_en;
ALTER TABLE turno DROP COLUMN IF EXISTS recordatorio_whatsapp;
