ALTER TABLE tracked_mangas
ADD COLUMN IF NOT EXISTS id uuid DEFAULT gen_random_uuid() UNIQUE;

CREATE TABLE IF NOT EXISTS manga_sources (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    manga_id uuid NOT NULL,
    provider_name varchar(30) NOT NULL,
    target_url text NOT NULL,
    is_active boolean DEFAULT TRUE,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_manga FOREIGN KEY (manga_id) REFERENCES tracked_mangas(id) ON DELETE CASCADE,
    CONSTRAINT unique_manga_provider UNIQUE (manga_id, provider_name)
);

CREATE INDEX IF NOT EXISTS idx_manga_sources_manga_id ON manga_sources(manga_id);
