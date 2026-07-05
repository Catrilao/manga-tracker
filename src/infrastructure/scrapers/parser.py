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

    Designed to work with different scanlation sources (API or DOM scraping).

    CONTRACT: This function is an objective observer. It intentionally
    does NOT filter out chapters with missing links, missing languages,
    or invalid numbers (-1.0). It constructs the Chapter objects as-is.
    Validation and filtering are strictly the responsibility of the
    database sync layer.
    """

    def _extract_number(self, text: str) -> Decimal | None:
        if not text:
            return None

        match = re.search(r"(?:Ch\.?|chapter)\s*(\d+(?:\.\d+)?)", text, flags=re.IGNORECASE)

        if not match:
            match = re.search(r"(\d+(?:\.\d+)?)", text, flags=re.IGNORECASE)

        if match:
            return Decimal(match.group(1))

        return None

    def __call__(
        self,
        manga_id: UUID,
        raw_chapters: tuple[RawChapter, ...],
    ) -> tuple[Chapter, ...]:
        logger.info("parsing_raw_chapters_started", target_manga_id=str(manga_id))

        parsed_chapters = []
        for ch in raw_chapters:
            number = Decimal("-1.0")

            extracted_number = self._extract_number(ch.raw_number)

            if extracted_number is None:
                extracted_number = self._extract_number(ch.raw_title)

            if extracted_number is not None:
                number = extracted_number
            else:
                logger.warning(
                    "chapter_number_parse_failed",
                    manga_id=str(manga_id),
                    raw_title=ch.raw_title,
                    raw_number=ch.raw_number,
                )

            name = "No name"
            if ch.raw_title:
                clean_name = re.sub(
                    r"^(?:Ch\.|chapter)\s*\d+(?:\.\d+)?\s*-\s*",
                    "",
                    ch.raw_title,
                    flags=re.IGNORECASE,
                )
                name = clean_name.strip() or "No name"

            try:
                language = ch.language_title.strip().lower()

                logger.debug(
                    "chapter_parsed",
                    manga_id=str(manga_id),
                    number=str(number),
                    name=name,
                    link=ch.href,
                    language=language,
                )

                chapter = Chapter(
                    manga_id=manga_id,
                    number=number,
                    name=name,
                    link=ch.href,
                    language=language,
                )
                parsed_chapters.append(chapter)
            except Exception as e:
                raise ParseError(f"Failed to coerce raw data into Chapter model: {str(e)}")

        return tuple(parsed_chapters)
