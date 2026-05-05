from __future__ import annotations

import html
import os
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class MarketTicker:
    symbol: str
    label: str


@dataclass(frozen=True)
class FredSeries:
    series_id: str
    label: str
    suffix: str = "%"


MARKET_TICKERS = [
    MarketTicker("^GSPC", "S&P 500"),
    MarketTicker("^NDX", "Nasdaq 100"),
    MarketTicker("^RUT", "Russell 2000"),
    MarketTicker("^VIX", "VIX"),
    MarketTicker("DX-Y.NYB", "DXY"),
    MarketTicker("KRW=X", "USD/KRW"),
    MarketTicker("JPY=X", "USD/JPY"),
    MarketTicker("CL=F", "WTI"),
    MarketTicker("GC=F", "Gold"),
    MarketTicker("HG=F", "Copper"),
    MarketTicker("^KS11", "KOSPI"),
    MarketTicker("^KQ11", "KOSDAQ"),
    MarketTicker("^N225", "Nikkei 225"),
    MarketTicker("^HSI", "Hang Seng"),
]

FRED_SERIES = [
    FredSeries("DGS2", "US 2Y"),
    FredSeries("DGS10", "US 10Y"),
    FredSeries("T10Y2Y", "10Y-2Y"),
    FredSeries("BAMLH0A0HYM2", "HY Spread"),
    FredSeries("SOFR", "SOFR"),
]


class ConfigError(RuntimeError):
    pass


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def require_env(name: str) -> str:
    value = env(name)
    if not value or value == "replace_me":
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value:+.2f}%"


def bp(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value:+.0f}bp"


def compact_number(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 100:
        return f"{value:.1f}"
    return f"{value:.2f}"


def section_market_rows(market: pd.DataFrame, labels: list[str]) -> list[str]:
    rows = []
    subset = market[market["label"].isin(labels)].copy()
    subset["order"] = subset["label"].map({label: i for i, label in enumerate(labels)})
    subset = subset.sort_values("order")
    for _, row in subset.iterrows():
        rows.append(
            f"- {html.escape(row['label'])}: {compact_number(row['latest'])}, "
            f"1D {pct(row['day_change'])}, 5D {pct(row['week_change'])}"
        )
    return rows


def fetch_market_snapshot() -> pd.DataFrame:
    symbols = [ticker.symbol for ticker in MARKET_TICKERS]
    data = yf.download(
        tickers=symbols,
        period="2mo",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )

    rows = []
    for ticker in MARKET_TICKERS:
        frame = pd.DataFrame()
        try:
            if isinstance(data.columns, pd.MultiIndex):
                frame = data[ticker.symbol].dropna(subset=["Close"])
            else:
                frame = data.dropna(subset=["Close"])
        except (KeyError, AttributeError, ValueError):
            continue

        if len(frame) < 2:
            continue

        close = frame["Close"]
        latest = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        day_change = (latest / prev - 1) * 100
        week_change = (latest / float(close.iloc[-6]) - 1) * 100 if len(close) >= 6 else None
        rows.append(
            {
                "label": ticker.label,
                "symbol": ticker.symbol,
                "latest": latest,
                "day_change": day_change,
                "week_change": week_change,
                "date": close.index[-1].strftime("%Y-%m-%d"),
            }
        )

    return pd.DataFrame(rows)


def fetch_fred_series(series: FredSeries, api_key: str) -> dict | None:
    end = datetime.now(ZoneInfo("UTC")).date()
    start = end - timedelta(days=45)
    response = requests.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={
            "series_id": series.series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": start.isoformat(),
            "sort_order": "asc",
        },
        timeout=20,
    )
    response.raise_for_status()
    observations = [
        row for row in response.json().get("observations", [])
        if row.get("value") not in (None, ".")
    ]
    if len(observations) < 2:
        return None

    latest = observations[-1]
    prev = observations[-2]
    latest_value = float(latest["value"])
    prev_value = float(prev["value"])
    return {
        "label": series.label,
        "series_id": series.series_id,
        "latest": latest_value,
        "change_bp": (latest_value - prev_value) * 100,
        "date": latest["date"],
        "suffix": series.suffix,
    }


def fetch_rates_snapshot() -> list[dict]:
    api_key = env("FRED_API_KEY")
    if not api_key or api_key == "replace_me":
        return []

    rows = []
    for series in FRED_SERIES:
        try:
            row = fetch_fred_series(series, api_key)
            if row:
                rows.append(row)
        except requests.RequestException:
            continue
    return rows


def get_change(market: pd.DataFrame, label: str) -> float | None:
    if market.empty or "label" not in market.columns:
        return None
    matched = market.loc[market["label"] == label, "day_change"]
    return None if matched.empty else float(matched.iloc[0])


def build_regime(market: pd.DataFrame, rates: list[dict]) -> tuple[str, list[str]]:
    score = 0
    notes: list[str] = []

    spx = get_change(market, "S&P 500")
    ndx = get_change(market, "Nasdaq 100")
    rut = get_change(market, "Russell 2000")
    vix = get_change(market, "VIX")
    dxy = get_change(market, "DXY")
    wti = get_change(market, "WTI")
    krw = get_change(market, "USD/KRW")

    if spx is not None:
        score += 1 if spx > 0.5 else -1 if spx < -0.5 else 0
        if spx > 0.5:
            notes.append("미국 대형주는 상승 우위로 마감했습니다.")
        elif spx < -0.5:
            notes.append("미국 대형주는 하락 압력이 우세했습니다.")
    if ndx is not None and rut is not None:
        if ndx > rut + 0.5:
            notes.append("대형 성장주가 중소형주보다 강합니다.")
        elif rut > ndx + 0.5:
            notes.append("중소형주가 상대적으로 강해 위험 선호 폭이 넓어졌습니다.")
    if vix is not None:
        score += 1 if vix < -3 else -1 if vix > 3 else 0
        if vix > 5:
            notes.append("VIX 상승 폭이 커 단기 헤지 수요가 늘었습니다.")
        elif vix < -5:
            notes.append("VIX가 크게 하락해 단기 불안은 완화됐습니다.")
    if dxy is not None:
        score += 1 if dxy < -0.3 else -1 if dxy > 0.3 else 0
        if dxy > 0.3:
            notes.append("달러 강세는 위험자산과 신흥국 통화에 부담입니다.")
        elif dxy < -0.3:
            notes.append("달러 약세는 글로벌 유동성 심리에 우호적입니다.")
    if krw is not None and krw > 0.4:
        notes.append("USD/KRW 상승으로 한국장 외국인 수급은 보수적으로 볼 필요가 있습니다.")
    if wti is not None and abs(wti) > 2:
        direction = "상승" if wti > 0 else "하락"
        notes.append(f"WTI가 {direction}해 에너지/인플레이션 민감 섹터를 확인해야 합니다.")

    ten_year = next((row for row in rates if row["label"] == "US 10Y"), None)
    if ten_year:
        score += -1 if ten_year["change_bp"] > 5 else 1 if ten_year["change_bp"] < -5 else 0
        if ten_year["change_bp"] > 5:
            notes.append("미국 10년물 금리 상승은 밸류에이션 부담 요인입니다.")
        elif ten_year["change_bp"] < -5:
            notes.append("미국 10년물 금리 하락은 성장주 멀티플에 우호적입니다.")

    if score >= 2:
        regime = "Risk-on"
    elif score <= -2:
        regime = "Risk-off"
    else:
        regime = "Neutral"

    if not notes:
        notes.append("방향성은 혼재되어 있어 확인 장세에 가깝습니다.")

    return regime, notes


def build_watch_items(market: pd.DataFrame, rates: list[dict]) -> list[str]:
    items = []
    vix = get_change(market, "VIX")
    dxy = get_change(market, "DXY")
    krw = get_change(market, "USD/KRW")
    ten_two = next((row for row in rates if row["label"] == "10Y-2Y"), None)

    if vix is not None and vix > 3:
        items.append("VIX 추가 상승 여부")
    if dxy is not None and dxy > 0.3:
        items.append("달러 강세 지속 여부")
    if krw is not None and krw > 0.4:
        items.append("USD/KRW와 외국인 수급")
    if ten_two and abs(ten_two["change_bp"]) >= 3:
        items.append("장단기 금리차 변화")
    if not items:
        items.extend(["미국 선물 흐름", "USD/KRW", "반도체/성장주 상대강도"])
    return items[:4]


def format_report(market: pd.DataFrame, rates: list[dict]) -> str:
    if market.empty:
        raise RuntimeError("No market data was downloaded.")

    tz_name = env("TIMEZONE", "Asia/Seoul")
    now = datetime.now(ZoneInfo(tz_name))
    title = env("REPORT_TITLE", "Daily Macro Brief")
    regime, notes = build_regime(market, rates)
    watch_items = build_watch_items(market, rates)

    lines = [
        f"<b>{html.escape(title)}</b>",
        f"{now:%Y-%m-%d %H:%M} {html.escape(tz_name)}",
        "",
        f"<b>시장 톤:</b> {html.escape(regime)}",
        "",
        "<b>주요 시장</b>",
    ]

    lines.extend(section_market_rows(market, ["S&P 500", "Nasdaq 100", "Russell 2000", "VIX"]))
    lines.extend(["", "<b>환율/원자재</b>"])
    lines.extend(section_market_rows(market, ["DXY", "USD/KRW", "USD/JPY", "WTI", "Gold", "Copper"]))
    lines.extend(["", "<b>아시아</b>"])
    lines.extend(section_market_rows(market, ["KOSPI", "KOSDAQ", "Nikkei 225", "Hang Seng"]))

    if rates:
        lines.extend(["", "<b>금리/크레딧</b>"])
        for row in rates:
            lines.append(
                f"- {html.escape(row['label'])}: {row['latest']:.2f}{html.escape(row['suffix'])} "
                f"({bp(row['change_bp'])})"
            )

    lines.extend(["", "<b>해석</b>"])
    for note in notes:
        lines.append(f"- {html.escape(note)}")

    lines.extend(["", "<b>체크포인트</b>"])
    for item in watch_items:
        lines.append(f"- {html.escape(item)}")
    lines.extend(["", "<i>자동 생성 리포트입니다. 투자 판단은 별도 검증이 필요합니다.</i>"])
    return "\n".join(lines)


def split_message(message: str, limit: int = 3800) -> list[str]:
    if len(message) <= limit:
        return [message]

    chunks: list[str] = []
    current = ""
    for line in message.splitlines():
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def send_telegram(message: str, chat_id: str | None = None) -> None:
    token = require_env("TELEGRAM_BOT_TOKEN")
    target_chat_id = chat_id or require_env("TELEGRAM_CHAT_ID")
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": target_chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=20,
    )
    response.raise_for_status()


def notify_error(error: BaseException) -> None:
    error_chat_id = env("ERROR_CHAT_ID") or env("TELEGRAM_CHAT_ID")
    if not error_chat_id:
        return

    detail = "".join(traceback.format_exception_only(type(error), error)).strip()
    message = (
        "<b>Daily Macro Brief failed</b>\n"
        f"<pre>{html.escape(detail[:1200])}</pre>"
    )
    try:
        send_telegram(message, chat_id=error_chat_id)
    except Exception:
        pass


def main() -> None:
    try:
        market = fetch_market_snapshot()
        rates = fetch_rates_snapshot()
        report = format_report(market, rates)
        print(report)

        if env("DRY_RUN").lower() in {"1", "true", "yes"}:
            return

        for chunk in split_message(report):
            send_telegram(chunk)
    except Exception as error:
        notify_error(error)
        print(f"ERROR: {error}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
