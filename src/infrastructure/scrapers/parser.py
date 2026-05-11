import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin
from uuid import UUID

from src.domain.models import Chapter, ParseError, RawChapter
from src.logger import get_logger

logger = get_logger(__name__)


class MangadexChapterParser:
    """
    Fulfills the ChapterParserPort.
    Transforms raw, unvalidated strings from the JS evaluation into strict Domain Models.

    CONTRACT: This function is an objective observer. It intentionally
    does NOT filter out chapters with missing links, missing languages,
    or invalid numbers (-1.0). It constructs the Chapter objects as-is.
    Validation and filtering are strictly the responsibility of the
    database sync layer.
    """

    def __call__(
        self,
        manga_id: UUID,
        raw_chapters: tuple[RawChapter, ...],
        base_url: str = "https://mangadex.org",
    ) -> tuple[Chapter, ...]:
        logger.info("parsing_raw_chapters_started", target_manga_id=str(manga_id))

        parsed_chapters = []
        for raw in raw_chapters:
            number = Decimal("-1.0")
            name = raw.info_text.strip() if raw.info_text else "No name"

            if raw.header_text:
                num_match = re.search(
                    r"(\d+(?:\.\d+)?)",
                    raw.header_text,
                    re.IGNORECASE,
                )
                if num_match:
                    try:
                        number = Decimal(num_match.group(1))
                    except InvalidOperation:
                        pass

            if number == Decimal("-1.0"):
                num_match = re.search(
                    r"(?:Ch\.?|chapter)\s*(\d+(?:\.\d+)?)",
                    raw.info_text,
                    re.IGNORECASE,
                )
                if num_match:
                    try:
                        number = Decimal(num_match.group(1))
                    except InvalidOperation:
                        pass

            name_match = re.search(
                r"(Ch\.|chapter)\s*\d+(?:\.\d+)?\s*-\s*(.+)",
                raw.info_text,
                re.IGNORECASE,
            )
            if name_match:
                name = name_match.group(2).strip()

            chapter_link = raw.href
            if chapter_link and not chapter_link.startswith("https"):
                chapter_link = urljoin(base_url, chapter_link)

            logger.debug(
                "chapter_parsed",
                manga_id=str(manga_id),
                number=str(number),
                name=name,
                link=chapter_link,
                language=raw.language_title,
            )

            if not chapter_link or number == Decimal("-1.0"):
                logger.warning(
                    "empty_chapter_info",
                    manga_id=str(manga_id),
                    chapter_name=name or "Unknown",
                    has_link=bool(chapter_link),
                )

            try:
                chapter = Chapter(
                    manga_id=manga_id,
                    number=number,
                    name=name,
                    link=chapter_link,
                    language=raw.language_title,
                )
                parsed_chapters.append(chapter)
            except Exception as e:
                raise ParseError(f"Failed to coerce raw data into Chapter model: {str(e)}")

        return tuple(parsed_chapters)
