-- notification_settings schema (idempotent)
CREATE TABLE IF NOT EXISTS notification_settings (
    user_id BIGINT PRIMARY KEY,
    mute_all BOOLEAN NOT NULL DEFAULT FALSE,
    mute_types TEXT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);
