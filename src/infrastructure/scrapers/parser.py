import re
from decimal import Decimal
from uuid import UUID

from src.domain.models import Chapter, ParseError, RawChapter
from src.logger import get_logger

logger = get_logger(__name__)


class GenericParser:
    """
    Fulfills the ChapterParserPort.
    Transforms raw, unvalidated strings from the JS evaluation into strict Domain Models.

    Designed to work with different scanlation sources.

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
    ) -> tuple[Chapter, ...]:
        logger.info("parsing_raw_chapters_started", target_manga_id=str(manga_id))

        parsed_chapters = []
        for raw in raw_chapters:
            number = Decimal("-1.0")
            name = raw.info_text.strip() if raw.info_text else "No name"

            if raw.header_text:
                num_match = re.search(
                    r"(?:Ch\.?|chapter)\s*(\d+(?:\.\d+)?)",
                    raw.header_text,
                    re.IGNORECASE,
                )
                if num_match:
                    number = Decimal(num_match.group(1))

            if number == Decimal("-1.0"):
                num_match = re.search(
                    r"(?:Ch\.?|chapter)\s*(\d+(?:\.\d+)?)",
                    raw.info_text,
                    re.IGNORECASE,
                )
                if num_match:
                    number = Decimal(num_match.group(1))

            name_match = re.search(
                r"(Ch\.|chapter)\s*\d+(?:\.\d+)?\s*-\s*(.+)",
                raw.info_text,
                re.IGNORECASE,
            )
            if name_match:
                name = name_match.group(2).strip()

            if number == Decimal("-1.0"):
                logger.warning(
                    "chapter_number_parse_failed",
                    manga_id=str(manga_id),
                    raw_header=raw.header_text,
                    raw_info=raw.info_text,
                )

            logger.debug(
                "chapter_parsed",
                manga_id=str(manga_id),
                number=str(number),
                name=name,
                link=raw.href,
                language=raw.language_title,
            )

            try:
                chapter = Chapter(
                    manga_id=manga_id,
                    number=number,
                    name=name,
                    link=raw.href,
                    language=raw.language_title,
                )
                parsed_chapters.append(chapter)
            except Exception as e:
                raise ParseError(f"Failed to coerce raw data into Chapter model: {str(e)}")

        return tuple(parsed_chapters)
