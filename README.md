# MangaDex Tracker

[![License: MIT](https://img.shields.io/badge/License-MIT-red.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-gren.svg)](https://www.python.org/)
[![CI](https://github.com/Catrilao/manga-tracker/actions/workflows/ci.yaml/badge.svg)](https://github.com/Catrilao/manga-tracker/actions/workflows/ci.yaml)

An automated scraper that monitors MangaDex for new chapter releases of tracked mangas and sends notifications via Discord. Built with Python and PostgreSQL.

## Features

- **Hexagonal Architecture**: Clear separation of domain logic, use cases, and infrastructure.
- **Reproducible Environments**: Dependency management via `uv` and declarative environments via Nix flakes.
- **Zero-Trust CI/CD**: Ready for GitHub Actions with dynamic database firewall whitelisting (e.g., Supabase network restrictions).
- **Data Quality Gatekeeper**: Built-in anomaly detection to prevent syncing when the API behaves unexpectedly or regional geo-blocks occur.

## Requirements

- **Python 3.12+**
- **[uv](https://github.com/astral-sh/uv)**
- **PostgreSQL Database**
- _(Optional)_ **Nix** (for the reproducible `nix develop` shell).

## Installation

1. **Clone the repository**:

   ```bash
   # Using HTTPS
   git clone https://github.com/Catrilao/manga-tracker.git

   # Or using SSH
   git clone git@github.com:Catrilao/manga-tracker.git

   cd manga-tracker
   ```

2. **Sync the environment**:

```bash
uv sync

```

## Development

This project uses `pre-commit` to enforce code quality, type checking (`mypy`), and consistent formatting (`ruff`).

Before starting to push code, install the pre-commit hooks:

```
uv run pre-commit install
```

## Usage

Execute the tracker via the CLI entrypoint defined in the project:

```bash
uv run manga-tracker

```

## Environment Variables

Add the following to a `.env` file or export them directly in your environment:

- `DATABASE_URL`: Full PostgreSQL connection string (e.g., `postgresql://user:pass@host:6543/db`).
- `DISCORD_WEBHOOK`: Discord Webhook URL for error and chapter notifications.
- `TRACKER_ENV`: Environment context (e.g., `test` or `production`) which determines logging format and behavior.

## Logic & Cold Start

The tracker uses a **Cold Start** strategy to prevent notification spam during initialization:

1. **Initial Run**: If a tracked manga is scraped for the first time, the database populates all existing chapters silently to establish a baseline.
2. **Subsequent Runs**: Notifications are only triggered when a newly scraped `(chapter_number, language)` pair is detected and successfully committed to the database.
