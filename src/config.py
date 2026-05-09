import os
from dataclasses import dataclass

from src.domain.models import ConfigurationError


@dataclass(frozen=True)
class AppConfig:
    db_user: str
    db_password: str
    db_host: str
    db_port: int
    db_name: str
    discord_webhook_url: str


def load_config() -> AppConfig:
    required_vars = [
        "DB_USER",
        "DB_PASSWORD",
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
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

    try:
        parsed_port = int(values["DB_PORT"])
    except ValueError as err:
        raise ConfigurationError(
            f"'DB_PORT' must be an integer, got '{values['DB_PORT']}'"
        ) from err

    return AppConfig(
        db_user=values["DB_USER"],
        db_password=values["DB_PASSWORD"],
        db_host=values["DB_HOST"],
        db_port=parsed_port,
        db_name=values["DB_NAME"],
        discord_webhook_url=values["DISCORD_WEBHOOK"],
    )
