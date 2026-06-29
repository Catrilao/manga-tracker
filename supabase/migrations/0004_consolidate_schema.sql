ALTER TABLE mangas ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

INSERT INTO mangas(id, name, thumbnail, url, is_active)
SELECT id, 'Unknown', '', '', is_active
FROM tracked_mangas
ON CONFLICT(id) DO NOTHING;

DROP INDEX IF EXISTS idx_manga_sources_manga_id;

ALTER TABLE manga_sources
DROP CONSTRAINT manga_sources_pkey,
DROP CONSTRAINT fk_manga,
ADD CONSTRAINT manga_sources_pkey PRIMARY KEY (manga_id, provider_name),
ADD CONSTRAINT fk_manga_sources_mangas
FOREIGN KEY(manga_id) REFERENCES mangas(id) ON DELETE CASCADE;

ALTER TABLE mangas
DROP COLUMN IF EXISTS url;

DROP TABLE IF EXISTS tracked_mangas;
