# MangaDex Tracker

An automated scraper that monitors MangaDex for new chapter releases of tracked mangas and sends notifications via Discord. Built with Python, Playwright, and PostgreSQL.

## Features

- **Hexagonal Architecture**: Clear separation of domain logic, use cases, and infrastructure.
- **Headless Scraping**: Uses Playwright with DOM wait states, dynamic network interception, and robust timeout handling.
- **Reproducible Environments**: Dependency management via `uv` and declarative environments via Nix flakes.
- **Zero-Trust CI/CD**: Ready for GitHub Actions with dynamic database firewall whitelisting (e.g., Supabase network restrictions).

## Requirements

- **Python 3.12+**
- **[uv](https://github.com/astral-sh/uv)**
- **PostgreSQL Database**
- _(Optional)_ **Nix** (for the reproducible `nix develop` shell).

## Installation

1. **Clone the repository**:

   ```bash
   git clone https://github.com/Catrilao/manga-tracker.git
   cd manga-tracker
   ```

2. **Sync the environment**:

```bash
uv sync

```

3. **Install Playwright Browsers**:

```bash
uv run playwright install chromium

```

_(Note: If using `nix develop .#ci`, the browser binary is handled automatically by Nix)._

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
