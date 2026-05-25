from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from bs4 import BeautifulSoup

from semiconductor_timing.agents.base import BaseAgent
from semiconductor_timing.config import get_settings
from semiconductor_timing.schemas import AgentMeta, FlowOutput


SAMSUNG = "005930"
HYNIX = "000660"
NAVER_NAMES = {
    SAMSUNG: "삼성전자",
    HYNIX: "SK하이닉스",
}


def yyyymmdd(date: datetime) -> str:
    return date.strftime("%Y%m%d")


def latest_value(frame: pd.DataFrame, column_candidates: list[str]) -> float | None:
    if frame is None or frame.empty:
        return None
    for candidate in column_candidates:
        if candidate in frame.columns:
            series = frame[candidate].dropna()
            if not series.empty:
                return float(series.iloc[-1])
    return None


def column_sum(frame: pd.DataFrame, column_candidates: list[str]) -> float | None:
    if frame is None or frame.empty:
        return None
    for candidate in column_candidates:
        if candidate in frame.columns:
            return float(frame[candidate].dropna().sum())
    return None


def to_billion_krw(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value / 100_000_000, 1)


def trend_score_from_value(value_billion: float | None) -> int | None:
    if value_billion is None:
        return None
    if value_billion >= 3000:
        return 4
    if value_billion >= 1000:
        return 3
    if value_billion > -1000:
        return 2
    if value_billion > -3000:
        return 1
    return 0


def get_latest_ohlcv(stock, ticker: str, start: str, end: str) -> float | None:
    frame = stock.get_market_ohlcv_by_date(start, end, ticker)
    return latest_value(frame, ["종가", "Close"])


def get_latest_pbr(stock, ticker: str, start: str, end: str) -> float | None:
    frame = stock.get_market_fundamental_by_date(start, end, ticker)
    return latest_value(frame, ["PBR"])


def get_short_ratio(stock, ticker: str, start: str, end: str) -> float | None:
    frame = stock.get_shorting_volume_by_date(start, end, ticker)
    if frame is None or frame.empty:
        return None
    ratio = latest_value(frame, ["비중", "공매도비중"])
    if ratio is not None:
        return round(ratio, 2)
    short_volume = latest_value(frame, ["공매도", "공매도수량"])
    volume = latest_value(frame, ["거래량"])
    if short_volume is not None and volume:
        return round(short_volume / volume * 100, 2)
    return None


def get_trading_value(stock, ticker: str, start: str, end: str) -> pd.DataFrame:
    return stock.get_market_trading_value_by_date(start, end, ticker)


def parse_int(text: str) -> int | None:
    value = text.replace(",", "").replace("+", "").strip()
    if not value or value in {"-", "N/A"}:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def parse_float(text: str) -> float | None:
    value = text.replace(",", "").replace("%", "").strip()
    if not value or value in {"-", "N/A"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def fetch_naver_investor_rows(ticker: str) -> list[dict]:
    url = f"https://finance.naver.com/item/frgn.naver?code={ticker}&page=1"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    target = None
    for table in soup.find_all("table"):
        text = table.get_text(" ", strip=True)
        if "외국인 기관 순매매" in text and "보유율" in text:
            target = table
            break
    if target is None:
        return []

    rows: list[dict] = []
    for tr in target.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) < 9 or not cells[0][:4].isdigit():
            continue
        close = parse_int(cells[1])
        volume = parse_int(cells[4])
        inst_net_shares = parse_int(cells[5])
        foreign_net_shares = parse_int(cells[6])
        holding_rate = parse_float(cells[8]) if len(cells) > 8 else None
        rows.append(
            {
                "date": cells[0],
                "close": close,
                "volume": volume,
                "institution_net_shares": inst_net_shares,
                "foreign_net_shares": foreign_net_shares,
                "foreign_holding_rate": holding_rate,
            }
        )
    return rows


def net_shares_to_billion(net_shares: int | None, close: int | None) -> float | None:
    if net_shares is None or close is None:
        return None
    return round(net_shares * close / 100_000_000, 1)


class FlowAgent(BaseAgent):
    name = "flow_tracker"

    def run(self) -> FlowOutput:
        settings = get_settings()
        try:
            from pykrx import stock
        except ImportError:
            return FlowOutput(
                meta=AgentMeta(
                    agent=self.name,
                    confidence=0.3,
                    fallback_used=True,
                    timestamp=datetime.now(ZoneInfo(settings.timezone)),
                )
            )

        now = datetime.now(ZoneInfo(settings.timezone))
        end = yyyymmdd(now)
        start = yyyymmdd(now - timedelta(days=45))
        fallback_count = 0

        samsung_flow = hynix_flow = kospi_flow = pd.DataFrame()
        try:
            samsung_flow = get_trading_value(stock, SAMSUNG, start, end)
            hynix_flow = get_trading_value(stock, HYNIX, start, end)
            kospi_flow = get_trading_value(stock, "KOSPI", start, end)
        except Exception:
            fallback_count += 1

        samsung_foreign = to_billion_krw(latest_value(samsung_flow, ["외국인합계", "외국인"]))
        hynix_foreign = to_billion_krw(latest_value(hynix_flow, ["외국인합계", "외국인"]))
        samsung_inst = to_billion_krw(latest_value(samsung_flow, ["기관합계", "기관"]))
        hynix_inst = to_billion_krw(latest_value(hynix_flow, ["기관합계", "기관"]))
        kospi_foreign = to_billion_krw(latest_value(kospi_flow, ["외국인합계", "외국인"]))

        combined_4week = None
        samsung_foreign_sum = column_sum(samsung_flow.tail(20), ["외국인합계", "외국인"])
        hynix_foreign_sum = column_sum(hynix_flow.tail(20), ["외국인합계", "외국인"])
        if samsung_foreign_sum is not None or hynix_foreign_sum is not None:
            combined_4week = to_billion_krw((samsung_foreign_sum or 0) + (hynix_foreign_sum or 0))

        try:
            samsung_close = get_latest_ohlcv(stock, SAMSUNG, start, end)
            hynix_close = get_latest_ohlcv(stock, HYNIX, start, end)
            samsung_pbr = get_latest_pbr(stock, SAMSUNG, start, end)
            hynix_pbr = get_latest_pbr(stock, HYNIX, start, end)
        except Exception:
            fallback_count += 1
            samsung_close = hynix_close = samsung_pbr = hynix_pbr = None

        try:
            samsung_rows = fetch_naver_investor_rows(SAMSUNG)
            hynix_rows = fetch_naver_investor_rows(HYNIX)
            if samsung_rows:
                latest = samsung_rows[0]
                samsung_close = samsung_close or latest["close"]
                samsung_foreign = samsung_foreign if samsung_foreign is not None else net_shares_to_billion(
                    latest["foreign_net_shares"], latest["close"]
                )
                samsung_inst = samsung_inst if samsung_inst is not None else net_shares_to_billion(
                    latest["institution_net_shares"], latest["close"]
                )
            if hynix_rows:
                latest = hynix_rows[0]
                hynix_close = hynix_close or latest["close"]
                hynix_foreign = hynix_foreign if hynix_foreign is not None else net_shares_to_billion(
                    latest["foreign_net_shares"], latest["close"]
                )
                hynix_inst = hynix_inst if hynix_inst is not None else net_shares_to_billion(
                    latest["institution_net_shares"], latest["close"]
                )

            if combined_4week is None and (samsung_rows or hynix_rows):
                total = 0.0
                has_value = False
                for row in (samsung_rows or [])[:20]:
                    value = net_shares_to_billion(row["foreign_net_shares"], row["close"])
                    if value is not None:
                        total += value
                        has_value = True
                for row in (hynix_rows or [])[:20]:
                    value = net_shares_to_billion(row["foreign_net_shares"], row["close"])
                    if value is not None:
                        total += value
                        has_value = True
                combined_4week = round(total, 1) if has_value else None
        except requests.RequestException:
            fallback_count += 1

        try:
            samsung_short = get_short_ratio(stock, SAMSUNG, start, end)
            hynix_short = get_short_ratio(stock, HYNIX, start, end)
        except Exception:
            fallback_count += 1
            samsung_short = hynix_short = None

        missing = sum(
            value is None
            for value in [
                samsung_foreign,
                hynix_foreign,
                samsung_inst,
                kospi_foreign,
                samsung_close,
                hynix_close,
                samsung_pbr,
                hynix_pbr,
            ]
        )
        confidence = max(0.3, 1 - missing * 0.07 - fallback_count * 0.10)

        return FlowOutput(
            meta=AgentMeta(
                agent=self.name,
                confidence=round(confidence, 2),
                fallback_used=fallback_count > 0 or missing > 0,
                timestamp=now,
            ),
            samsung_foreign_net_buy_billion=samsung_foreign,
            hynix_foreign_net_buy_billion=hynix_foreign,
            samsung_inst_net_buy_billion=samsung_inst,
            hynix_inst_net_buy_billion=hynix_inst,
            kospi_foreign_net_buy_billion=kospi_foreign,
            foreign_4week_trend_score=trend_score_from_value(combined_4week),
            samsung_short_ratio_pct=samsung_short,
            hynix_short_ratio_pct=hynix_short,
            samsung_close=samsung_close,
            hynix_close=hynix_close,
            samsung_pbr=samsung_pbr,
            hynix_pbr=hynix_pbr,
        )
