# MangaDex Tracker
Automated tracker designed to nofity via discord notifications of new releases of Dai Dark.

## Requirements
- **Python 3.12+**
- **[uv](https://github.com/astral-sh/uv)**

## Installation

1. **Clone the repository**:
   ```sh
   git clone <repo>
   ```

2. **Sync the environment**:
   ```bash
   uv sync
   ```
3. **Install Playwright Browsers**:
   ```bash
   uv run playwright install chromium
   ```

4. **Usage**
   ```bash
   uv run main.py
   ```

## Environment Variables
Add the following the `.env` file or GitHub Secrets:
- `USER`: Supabase database user.
- `PASSWORD`: Database password.
- `HOST`: Project's host (from Supabase Database settings).
- `PORT`: `6543` for connection pooling.
- `DISCORD_WEBHOOK`: Discord Webhook URL.

## Logic & Cold Start
The tracker uses a **Cold Start** logic to prevent notification spam:
1. **Initial Run**: If the database is empty, it populates all existing chapters silently to establish a baseline.
2. **Subsequent Runs**: Notifications are only triggered when a new `(number, language)` pair is inserted into the cloud database.
