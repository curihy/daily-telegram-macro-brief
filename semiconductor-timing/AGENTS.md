# Semiconductor Timing MVP

## Project Goal

Build a daily Korean semiconductor timing report for Samsung Electronics, SK Hynix, and the Jensen Universe.

The current MVP collects DRAM/HBM, market, and macro data; computes main and Jensen Universe scores; validates them; stores results in SQLite; and sends a Telegram report.

## Commands

```bash
cd /Users/hyeyoung/Documents/Codex/2026-05-05/telegram/semiconductor-timing
source .venv/bin/activate
python -m pytest tests -q
DRY_RUN=1 python scripts/run_daily.py
DRY_RUN=0 python scripts/run_daily.py
```

## Rules

- Do not commit `.env`, `data/*.db`, `.venv`, `.DS_Store`, or `-envv`.
- Keep secrets in `.env` only.
- Prefer small, testable changes.
- Run `python -m pytest tests -q` after code changes.
- Use `requirements.txt` for local dependency installation.
- Keep the MVP focused: Agent 2/3, scoring, validation, SQLite, and Telegram first.
- TrendForce/DRAMeXchange detailed data may be membership-gated; keep public scraping best-effort and fallback-friendly.

## Key Files

- `scripts/run_daily.py`: pipeline entry point
- `src/semiconductor_timing/agents/`: data collection agents
- `src/semiconductor_timing/agents/dram_agent.py`: TrendForce DDR5 + D램/HBM news collection
- `src/semiconductor_timing/scoring/calculators.py`: scoring logic
- `src/semiconductor_timing/validator/validator.py`: validation passes
- `src/semiconductor_timing/report/text_report.py`: Telegram report format
- `src/semiconductor_timing/delivery/telegram.py`: Telegram sender
- `src/semiconductor_timing/db/history.py`: SQLite persistence
