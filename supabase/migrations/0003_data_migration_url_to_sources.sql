DO $$
BEGIN
    IF EXISTS (
        SELECT
            1
        FROM
            information_schema.columns
        WHERE
            table_name = 'tracked_mangas'
            AND column_name = 'url'
    ) THEN
        INSERT INTO manga_sources (manga_id, provider_name, target_url, is_active)
        SELECT
            id AS manga_id,
            CASE
                WHEN url LIKE '%mangadex.org%' THEN 'mangadex'
                ELSE 'unknown'
            END AS provider_name,
            url AS target_url,
            TRUE AS is_active
        FROM
            tracked_mangas
        ON CONFLICT (manga_id, provider_name) DO NOTHING;
    END IF;
END $$
