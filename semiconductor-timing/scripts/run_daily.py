from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from semiconductor_timing.agents.dram_agent import DramAgent
from semiconductor_timing.agents.flow_agent import FlowAgent
from semiconductor_timing.agents.macro_agent import MacroAgent
from semiconductor_timing.agents.nvidia_agent import NvidiaAgent
from semiconductor_timing.config import get_settings
from semiconductor_timing.db.history import save_daily_result
from semiconductor_timing.delivery.telegram import send_telegram
from semiconductor_timing.report.text_report import render_report
from semiconductor_timing.schemas import DailyResult
from semiconductor_timing.scoring.calculators import calculate_jensen_score, calculate_main_score
from semiconductor_timing.validator.validator import pass1_integrity, pass2_consistency, summarize_validation


def main() -> None:
    settings = get_settings()
    dram = DramAgent().run()
    nvidia = NvidiaAgent().run()
    macro = MacroAgent().run()
    flow = FlowAgent().run()
    main_score = calculate_main_score(nvidia, macro, dram, flow)
    jensen_score = calculate_jensen_score(nvidia)
    validation = summarize_validation([
        pass1_integrity(nvidia, macro, dram, flow),
        pass2_consistency(main_score, jensen_score),
    ])

    result = DailyResult(
        run_at=datetime.now(ZoneInfo(settings.timezone)),
        dram=dram,
        nvidia=nvidia,
        macro=macro,
        flow=flow,
        main_score=main_score,
        jensen_score=jensen_score,
        validation=validation,
        report_text="",
    )
    report = render_report(result)
    result.report_text = report
    save_daily_result(settings.db_path, result)
    print(report)

    if not settings.dry_run:
        send_telegram(settings.telegram_bot_token, settings.telegram_chat_id, report)


if __name__ == "__main__":
    main()
