-- notifications table adjustments
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NULL;
