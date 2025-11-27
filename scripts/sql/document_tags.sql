-- document_tags schema (idempotent)
CREATE TABLE IF NOT EXISTS document_tags (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL,
    tag TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_document_tags_doc ON document_tags(document_id);
CREATE INDEX IF NOT EXISTS idx_document_tags_tag ON document_tags(tag);
