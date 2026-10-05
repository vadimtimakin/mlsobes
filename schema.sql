-- Схема загрузок собесов (Postgres). Идемпотентно: прогоняется при старте.

-- Одна загруженная запись = один собес (после обработки).
CREATE TABLE IF NOT EXISTS uploads (
    id             BIGSERIAL PRIMARY KEY,
    company_id     TEXT NOT NULL,
    company_name   TEXT NOT NULL,
    sector         TEXT NOT NULL,
    department     TEXT,
    interview_date DATE,
    comment        TEXT,
    note_md        TEXT NOT NULL,
    contributor    TEXT,
    status         TEXT NOT NULL DEFAULT 'live',  -- live | hidden
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Вытащенные из собеса вопросы (для навигатора).
CREATE TABLE IF NOT EXISTS upload_questions (
    id        BIGSERIAL PRIMARY KEY,
    upload_id BIGINT NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
    ord       INT NOT NULL,
    text      TEXT NOT NULL,
    pool_ids  JSONB NOT NULL DEFAULT '[]',
    domains   JSONB NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_upload_questions_upload ON upload_questions(upload_id);

-- Фоновые джобы обработки (для статуса на фронте).
CREATE TABLE IF NOT EXISTS jobs (
    id         TEXT PRIMARY KEY,                  -- uuid
    status     TEXT NOT NULL DEFAULT 'queued',    -- queued|transcribing|extracting|saving|done|error
    stage      TEXT,                              -- человекочитаемая стадия
    message    TEXT,                              -- текст ошибки / результат
    upload_id  BIGINT REFERENCES uploads(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
