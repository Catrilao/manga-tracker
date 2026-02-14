import os
import re
from dataclasses import dataclass

import psycopg2
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright


@dataclass
class Chapter:
    manga_id: str
    number: float
    name: str
    link: str
    language: str


def fetch_info_chapter(manga_url: str) -> list[Chapter]:
    all_chapters = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/118.0.5993.117 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="es-ES",
            color_scheme="light",
        )
        page = context.new_page()

        page.route("**/*.{png,jpg,jpeg,svg,css,woff,fnt}", lambda route: route.abort())

        page.goto(manga_url)
        page.wait_for_selector(".line-clamp-1")

        chapter_list = page.locator(".chapter.relative.read").all()

        number = -1
        name = "No name"
        link = manga_url
        language = "No language"
        uuid_match = re.search(r"/title/([0-9a-fA-F-]{36})", manga_url)
        manga_id = uuid_match.group(1) if uuid_match else ""

        for chapter in chapter_list:
            number = -1
            chapter_info = (
                chapter.locator(".line-clamp-1").first.text_content() or ""
            ).strip()
            name = chapter_info

            card = chapter.locator(
                "xpath=ancestor::div[contains(@class, 'bg-accent')][1]"
            )
            chapter_header = card.locator(
                ".chapter-header .font-bold.self-center.whitespace-nowrap"
            )
            if chapter_header.count() > 0:
                chapter_header_text = chapter_header.first.text_content() or ""
                num_match = re.search(
                    r"(\d+(?:\.\d+)?)",
                    chapter_header_text,
                )
                if num_match:
                    number = float(num_match.group(1))

            if number == -1:
                num_match = re.search(
                    r"(?:Ch\.?|chapter)\s*(\d+(?:\.\d+)?)",
                    chapter_info,
                    re.IGNORECASE,
                )
                if num_match:
                    number = float(num_match.group(1))

                name_match = re.search(
                    r"(Ch\.|chapter)\s*\d+(?:\.\d+)?\s*(?:-\s*)?(.+)",
                    chapter_info,
                    re.IGNORECASE,
                )
                if name_match:
                    name = name_match.group(2).strip()

            anchor_tag = chapter.locator("a[href*='/chapter/']").first
            link = anchor_tag.get_attribute("href") or ""
            language = anchor_tag.locator("img").first.get_attribute("title") or ""
            number = int(number) if number.is_integer() else number

            all_chapters.append(
                Chapter(
                    manga_id,
                    number,
                    name,
                    link,
                    language,
                )
            )
            print(f"{manga_id=}")
            print(f"{number=}")
            print(f"{name=}")
            print(f"{link=}")
            print(f"{language=}")

        context.close()
        browser.close()

    return all_chapters


def store_chapter_data(chapters_list: list[Chapter]) -> None:
    USER = os.getenv("user")
    PASSWORD = os.getenv("password")
    HOST = os.getenv("host")
    PORT = os.getenv("port")
    DATABASE = os.getenv("dbname")

    connection = None
    cursor = None
    try:
        connection = psycopg2.connect(
            user=USER,
            password=PASSWORD,
            host=HOST,
            port=PORT,
            database=DATABASE,
        )
        connection.autocommit = True
        cursor = connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chapters(
                manga_id TEXT,
                number NUMERIC,
                name VARCHAR(100),
                language VARCHAR(30),
                link TEXT,
                notified BOOLEAN DEFAULT FALSE,
                insert_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(manga_id, number, language)
            );
            """
        )

        cursor.execute("SELECT COUNT(*) FROM chapters;")
        result = cursor.fetchone()
        is_cold_start = (result[0] == 0) if result else True

        for chapter in chapters_list:
            cursor.execute(
                """
                INSERT INTO chapters 
                (manga_id, number, name, language, link)
                VALUES(%s, %s, %s, %s, %s)
                ON CONFLICT (manga_id, number, language) DO NOTHING
                RETURNING 1;
                """,
                (
                    chapter.manga_id,
                    chapter.number,
                    chapter.name,
                    chapter.language,
                    chapter.link,
                ),
            )
            inserted = cursor.fetchone() is not None

            if inserted and not is_cold_start:
                success = send_notification(chapter)
                if success:
                    cursor.execute(
                        """
                        UPDATE chapters
                        SET notified = TRUE
                        WHERE manga_id = %s AND number = %s AND language = %s
                        """,
                        (chapter.manga_id, chapter.number, chapter.language),
                    )

        connection.commit()
    except Exception as e:
        if connection:
            connection.rollback()
        print(f"Error: {e}")
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def send_notification(chapter: Chapter) -> bool:
    webhook = os.getenv("DISCORD_WEBHOOK") or ""

    embed = {
        "title": f" Dai Dark - Chapter {chapter.number} - {chapter.name}",
        "url": f"https://mangadex.org{chapter.link}",
        "color": 0xAC5F29,
        "fields": [
            {"name": "Language", "value": chapter.language, "inline": True},
        ],
        "footer": {"text": "MangaDex Notifier"},
        "thumbnail": {
            "url": "https://mangadex.org/covers/84703c86-eb83-45ec-8fc5-f34a25115893/e3a1e78b-7147-45f3-9c7f-ee398fa9c437.jpg"
        },
    }
    payload = {"embeds": [embed]}

    try:
        response = requests.post(webhook, json=payload, timeout=10)
        if response.status_code == 204:
            return True
        else:
            print(f"Error Discord: {response.status_code} {response.text}")
            return False
    except requests.RequestException as e:
        print(f"Connection error: {e}")
        return False


def send_error_notification(error_message: str):
    webhook = os.getenv("DISCORD_WEBHOOK") or ""

    embed = {
        "title": "Health Check: Error in the Tracker",
        "description": f"```python\n{error_message}\n```",
        "color": 0xAC5F29,
        "footer": {"text": "MangaDex Notifier - Error Log"},
    }
    payload = {"embeds": [embed]}

    try:
        response = requests.post(webhook, json=payload, timeout=10)
        if response.status_code == 204:
            return True
        else:
            print(f"Error Discord: {response.status_code} {response.text}")
            return False
    except requests.RequestException as e:
        print(f"Connection error: {e}")
        return False


load_dotenv()


if __name__ == "__main__":
    MANGA_URL = "https://mangadex.org/title/84703c86-eb83-45ec-8fc5-f34a25115893"

    try:
        chapters = fetch_info_chapter(MANGA_URL)
        if not chapters:
            raise Exception("No chapters found")

        store_chapter_data(chapters)
        print("Execution successful")
    except Exception as e:
        print(f"Error detected: {e}")
        send_error_notification(str(e))
