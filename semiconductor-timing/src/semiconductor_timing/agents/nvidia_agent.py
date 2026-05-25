from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from semiconductor_timing.agents.base import BaseAgent
from semiconductor_timing.config import get_settings
from semiconductor_timing.schemas import AgentMeta, NvidiaSoxOutput, TickerSnapshot


JENSEN_UNIVERSE = [
    ("MRVL", "Marvell Technology", "네트워킹", 2),
    ("LITE", "Lumentum Holdings", "포토닉스", 2),
    ("COHR", "Coherent Corp", "포토닉스", 2),
    ("CRWV", "CoreWeave", "클라우드", 2),
    ("NBIS", "Nebius Group", "클라우드", 2),
    ("INTC", "Intel", "제조", 2),
    ("SNPS", "Synopsys", "설계도구", 2),
    ("DELL", "Dell Technologies", "AI서버", 1),
    ("ALAB", "Astera Labs", "연결성", 1),
    ("CDNS", "Cadence Design Systems", "설계도구", 1),
    ("UBER", "Uber Technologies", "모빌리티", 1),
    ("QCOM", "Qualcomm", "모바일칩", 1),
    ("SIE.DE", "Siemens AG", "산업자동화", 1),
]

CORE_TICKERS = [
    ("NVDA", "Nvidia", "AI GPU", 2),
    ("^SOX", "SOX", "반도체지수", 2),
    ("SOXX", "SOXX ETF", "반도체 ETF", 1),
    ("SMH", "SMH ETF", "반도체 ETF", 1),
    ("005930.KS", "Samsung Electronics", "한국 반도체", 2),
    ("000660.KS", "SK Hynix", "한국 반도체", 2),
    ("091160.KS", "KODEX Semiconductor", "소부장 ETF", 1),
]


def rsi(series: pd.Series, period: int = 14) -> float | None:
    if len(series) < period + 1:
        return None
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    if loss.iloc[-1] == 0:
        return 100.0
    rs = gain.iloc[-1] / loss.iloc[-1]
    return float(100 - (100 / (1 + rs)))


def pct_change(close: pd.Series, periods: int) -> float | None:
    if len(close) <= periods:
        return None
    return float((close.iloc[-1] / close.iloc[-1 - periods] - 1) * 100)


def build_snapshot(ticker: str, name: str, category: str, weight: int, frame: pd.DataFrame) -> TickerSnapshot:
    frame = frame.dropna(subset=["Close"])
    if frame.empty:
        return TickerSnapshot(ticker=ticker, name=name, category=category, tier_weight=weight)

    close = frame["Close"]
    volume = frame["Volume"] if "Volume" in frame else pd.Series(dtype=float)
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()
    volume_ratio = None
    if len(volume.dropna()) >= 20 and volume.rolling(20).mean().iloc[-1]:
        volume_ratio = float(volume.iloc[-1] / volume.rolling(20).mean().iloc[-1])

    return TickerSnapshot(
        ticker=ticker,
        name=name,
        category=category,
        tier_weight=weight,
        close=float(close.iloc[-1]),
        change_1d_pct=pct_change(close, 1),
        change_5d_pct=pct_change(close, 5),
        change_20d_pct=pct_change(close, 20),
        rsi_14=rsi(close),
        above_50dma=bool(close.iloc[-1] > ma50.iloc[-1]) if len(close) >= 50 else None,
        above_200dma=bool(close.iloc[-1] > ma200.iloc[-1]) if len(close) >= 200 else None,
        volume_ratio_20d=volume_ratio,
    )


class NvidiaAgent(BaseAgent):
    name = "nvidia_sox"

    def run(self) -> NvidiaSoxOutput:
        settings = get_settings()
        ticker_specs = CORE_TICKERS + JENSEN_UNIVERSE
        symbols = [spec[0] for spec in ticker_specs]
        data = yf.download(
            symbols,
            period="1y",
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
        )

        snapshots: dict[str, TickerSnapshot] = {}
        fallback_count = 0
        for ticker, name, category, weight in ticker_specs:
            try:
                frame = data[ticker] if isinstance(data.columns, pd.MultiIndex) else data
                snapshots[ticker] = build_snapshot(ticker, name, category, weight, frame)
                if snapshots[ticker].close is None:
                    fallback_count += 1
            except Exception:
                fallback_count += 1
                snapshots[ticker] = TickerSnapshot(ticker=ticker, name=name, category=category, tier_weight=weight)

        universe = [snapshots[ticker] for ticker, *_ in JENSEN_UNIVERSE]
        etfs = [
            snapshots[ticker]
            for ticker in ["SOXX", "SMH", "005930.KS", "000660.KS", "091160.KS"]
            if ticker in snapshots
        ]
        confidence = max(0.3, 1 - fallback_count / max(1, len(ticker_specs)))
        return NvidiaSoxOutput(
            meta=AgentMeta(
                agent=self.name,
                confidence=confidence,
                fallback_used=fallback_count > 0,
                timestamp=datetime.now(ZoneInfo(settings.timezone)),
            ),
            nvda=snapshots.get("NVDA"),
            sox=snapshots.get("^SOX"),
            semiconductor_etfs=etfs,
            jensen_universe=universe,
        )
