-- document_revisions schema (idempotent)
CREATE TABLE IF NOT EXISTS document_revisions (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by BIGINT NULL,
    title TEXT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    reason TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_document_revisions_doc_created_at ON document_revisions(document_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_document_revisions_doc_hash ON document_revisions(document_id, content_hash);
