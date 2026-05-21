import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from src.domain.models import ConfigurationError

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class AppConfig:
    database_url: str
    discord_webhook_url: str
    chromium_executable_path: str | None


def load_config() -> AppConfig:
    required_vars = [
        "DATABASE_URL",
        "DISCORD_WEBHOOK",
    ]

    values = {}
    errors = []

    for var in required_vars:
        value = os.getenv(var)
        if not value or not value.strip():
            errors.append(var)
        else:
            values[var] = value.strip()

    if errors:
        missing_vars = ", ".join(errors)
        raise ConfigurationError(f"Missing required environmental variable(s): [{missing_vars}]")

    opt_chromium_path = os.getenv("CHROMIUM_EXECUTABLE_PATH")

    return AppConfig(
        database_url=values["DATABASE_URL"],
        discord_webhook_url=values["DISCORD_WEBHOOK"],
        chromium_executable_path=opt_chromium_path.strip() if opt_chromium_path else None,
    )


config = load_config()
