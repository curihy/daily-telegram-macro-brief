from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf

from semiconductor_timing.agents.base import BaseAgent
from semiconductor_timing.config import get_settings
from semiconductor_timing.schemas import AgentMeta, MacroOutput


def latest_fred(series_id: str, api_key: str) -> tuple[float | None, float | None]:
    if not api_key or api_key == "replace_me":
        return None, None
    end = datetime.now(ZoneInfo("UTC")).date()
    start = end - timedelta(days=45)
    response = requests.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": start.isoformat(),
            "sort_order": "asc",
        },
        timeout=20,
    )
    response.raise_for_status()
    rows = [row for row in response.json().get("observations", []) if row.get("value") not in (None, ".")]
    if len(rows) < 2:
        return None, None
    latest = float(rows[-1]["value"])
    previous = float(rows[-2]["value"])
    return latest, (latest - previous) * 100


def yahoo_change(symbol: str) -> tuple[float | None, float | None]:
    data = yf.download(symbol, period="2mo", interval="1d", auto_adjust=False, progress=False)
    if data.empty or "Close" not in data:
        return None, None
    close = data["Close"].dropna()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    if len(close) < 2:
        return None, None
    latest = float(close.iloc[-1])
    change = float((close.iloc[-1] / close.iloc[-2] - 1) * 100)
    return latest, change


class MacroAgent(BaseAgent):
    name = "macro_fed"

    def run(self) -> MacroOutput:
        settings = get_settings()
        fallback_count = 0

        try:
            us_10y, us_10y_change_bp = latest_fred("DGS10", settings.fred_api_key)
            us_2y, _ = latest_fred("DGS2", settings.fred_api_key)
        except requests.RequestException:
            us_10y, us_10y_change_bp, us_2y = None, None, None
            fallback_count += 1

        dxy, dxy_change = yahoo_change("DX-Y.NYB")
        usd_krw, usd_krw_change = yahoo_change("KRW=X")
        vix, vix_change = yahoo_change("^VIX")
        fallback_count += sum(value is None for value in [dxy, usd_krw, vix])

        spread = None
        if us_10y is not None and us_2y is not None:
            spread = us_10y - us_2y

        confidence = max(0.3, 1 - fallback_count / 4)
        return MacroOutput(
            meta=AgentMeta(
                agent=self.name,
                confidence=confidence,
                fallback_used=fallback_count > 0,
                timestamp=datetime.now(ZoneInfo(settings.timezone)),
            ),
            us_10y_yield=us_10y,
            us_2y_yield=us_2y,
            yield_curve_spread=spread,
            us_10y_change_bp=us_10y_change_bp,
            dxy=dxy,
            dxy_change_pct=dxy_change,
            usd_krw=usd_krw,
            usd_krw_change_pct=usd_krw_change,
            vix=vix,
            vix_change_pct=vix_change,
        )
