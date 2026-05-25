# Claude Code Notes

Follow `AGENTS.md` first.

This repository is safe to open and edit from Claude Code. The local virtual environment already exists at `.venv`, but recreate it if needed:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Before sending Telegram messages, confirm that `.env` contains:

```text
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=@daily_semicon_channel
FRED_API_KEY=...
DRY_RUN=0
```

Use `DRY_RUN=1 python scripts/run_daily.py` for safe local checks.
