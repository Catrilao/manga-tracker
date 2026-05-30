CREATE TABLE IF NOT EXISTS mangas(
    id UUID NOT NULL,
    name VARCHAR(100) NOT NULL CHECK (btrim(name) <> ''),
    thumbnail TEXT NOT NULL CHECK (btrim(thumbnail) <> ''),
    url TEXT NOT NULL CHECK (btrim(url) <> ''),
    PRIMARY KEY(id)
);

CREATE TABLE IF NOT EXISTS chapters(
    manga_id UUID NOT NULL,
    number NUMERIC NOT NULL CHECK (number >= 0),
    name VARCHAR(100) NOT NULL CHECK (btrim(name) <> ''),
    language VARCHAR(30) NOT NULL CHECK (btrim(language) <> ''),
    link TEXT NOT NULL CHECK (btrim(link) <> ''),
    notified BOOLEAN NOT NULL DEFAULT FALSE,
    inserted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (manga_id, number, language),
    FOREIGN KEY (manga_id) REFERENCES mangas(id)
);

CREATE TABLE IF NOT EXISTS  tracked_mangas(
url VARCHAR(255) PRIMARY KEY,
is_active BOOLEAN NOT NULL DEFAULT TRUE,
added_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS  scrape_runs(
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    run_id           UUID NOT NULL,
    gh_run_id        VARCHAR(50),
    git_commit       CHAR(40),

    started_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at      TIMESTAMPTZ,
    duration_ms      INT,

    manga_id         UUID NOT NULL,
    manga_name       VARCHAR(255),

    chapters_found   INT DEFAULT 0,
    chapters_new     INT DEFAULT 0,
    chapters_skipped INT DEFAULT 0,
    null_chapter_pct NUMERIC(5,2),

    status           VARCHAR(20) NOT NULL,
    http_status_code INT,
    error_class      VARCHAR(50),
    error_message    TEXT,

    metadata         JSONB DEFAULT '{}'::jsonb,
    notified_at      TIMESTAMPTZ,

    CONSTRAINT valid_duration CHECK (duration_ms >= 0),
    CONSTRAINT unique_manga_per_run UNIQUE(run_id, manga_id)
);
CREATE INDEX idx_scrape_runs_manga_date ON scrape_runs(manga_id, started_at DESC);
CREATE INDEX idx_scrape_runs_run_id ON scrape_runs(run_id);
