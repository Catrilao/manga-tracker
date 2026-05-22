INSERT INTO mangas (name, thumbnail, url) VALUES
	('Dai Dark', 'https://mangadex.org/covers/84703c86-eb83-45ec-8fc5-f34a25115893/e3a1e78b-7147-45f3-9c7f-ee398fa9c437.jpg.512.jpg', 'https://mangadex.org/title/84703c86-eb83-45ec-8fc5-f34a25115893'),
	('One Piece', 'https://mangadex.org/covers/a1c7c817-4e59-43b7-9365-09675a149a6f/2f4aca53-64c7-46ac-ae85-3bc9b3169890.png.512.jpg', 'https://mangadex.org/title/a1c7c817-4e59-43b7-9365-09675a149a6f')
ON CONFLICT(name) DO NOTHING;
