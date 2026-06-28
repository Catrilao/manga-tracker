INSERT INTO mangas (id, name, thumbnail, is_active)
VALUES
    ('84703c86-eb83-45ec-8fc5-f34a25115893', 'Manga A', 'https://placeholder.a.png', TRUE),
    ('a1c7c817-4e59-43b7-9365-09675a149a6f', 'Manga B', 'https://placeholder.b.png', TRUE)
ON CONFLICT(id) DO NOTHING;

INSERT INTO manga_sources (manga_id, provider_name, target_url, is_active)
VALUES
    ('84703c86-eb83-45ec-8fc5-f34a25115893', 'mangadex', 'https://mangadex.org/title/84703c86-eb83-45ec-8fc5-f34a25115893', TRUE),
    ('a1c7c817-4e59-43b7-9365-09675a149a6f', 'mangadex', 'https://mangadex.org/title/a1c7c817-4e59-43b7-9365-09675a149a6f', TRUE)
ON CONFLICT(manga_id, provider_name) DO NOTHING;
