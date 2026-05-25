from __future__ import annotations

from statistics import mean

from semiconductor_timing.schemas import DramHbmOutput, FlowOutput, JensenScore, MainScore, MacroOutput, NvidiaSoxOutput, TickerSnapshot


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def linear_score(value: float | None, bearish: float, bullish: float) -> float:
    if value is None:
        return 50.0
    if bullish == bearish:
        return 50.0
    return clamp((value - bearish) / (bullish - bearish) * 100)


def inverse_linear_score(value: float | None, good: float, bad: float) -> float:
    if value is None:
        return 50.0
    return clamp((bad - value) / (bad - good) * 100)


def action_from_score(score: float) -> str:
    if score >= 75:
        return "강한 매수 신호"
    if score >= 60:
        return "분할매수 검토"
    if score >= 40:
        return "관망"
    if score >= 25:
        return "비중 축소"
    return "매도·현금화"


def trend_score(trend: str) -> float:
    if trend == "상승":
        return 75.0
    if trend == "하락":
        return 25.0
    if trend == "보합":
        return 50.0
    return 50.0


def calculate_main_score(
    nvidia: NvidiaSoxOutput,
    macro: MacroOutput,
    dram: DramHbmOutput | None = None,
    flow: FlowOutput | None = None,
) -> MainScore:
    nvda = nvidia.nvda
    sox = nvidia.sox
    hynix = next((item for item in nvidia.semiconductor_etfs + nvidia.jensen_universe if item.ticker == "000660.KS"), None)
    dram = dram or DramHbmOutput(
        meta={"agent": "dram_hbm", "confidence": 0.3, "fallback_used": True, "timestamp": "1970-01-01T00:00:00Z"}
    )
    flow = flow or FlowOutput(
        meta={"agent": "flow_tracker", "confidence": 0.3, "fallback_used": True, "timestamp": "1970-01-01T00:00:00Z"}
    )

    factors = {
        "DDR5 현물": linear_score(dram.ddr5_spot_change_pct, -5, 5),
        "HBM 공급": linear_score(dram.hbm_supply_status, 0, 4),
        "D램 계약": trend_score(dram.ddr5_contract_trend),
        "외인 수급": linear_score(flow.foreign_4week_trend_score, 0, 4),
        "PBR 밸류": inverse_linear_score(flow.hynix_pbr, 1.0, 3.0),
        "NVDA 5D": linear_score(nvda.change_5d_pct if nvda else None, -8, 8),
        "SOX 5D": linear_score(sox.change_5d_pct if sox else None, -8, 8),
        "10Y 금리": inverse_linear_score(macro.us_10y_change_bp, -8, 8),
        "달러/원": inverse_linear_score(macro.usd_krw_change_pct, -1.5, 1.5),
        "VIX": inverse_linear_score(macro.vix_change_pct, -8, 8),
        "SK하이닉스": linear_score(hynix.change_5d_pct if hynix else None, -8, 8),
    }
    weights = {
        "DDR5 현물": 0.125,
        "HBM 공급": 0.125,
        "D램 계약": 0.075,
        "외인 수급": 0.10,
        "PBR 밸류": 0.05,
        "NVDA 5D": 0.15,
        "SOX 5D": 0.15,
        "10Y 금리": 0.10,
        "달러/원": 0.08,
        "VIX": 0.07,
        "SK하이닉스": 0.025,
    }
    score = sum(factors[key] * weights[key] for key in factors)
    weakest = min(factors, key=factors.get)
    strongest = max(factors, key=factors.get)
    return MainScore(
        score=round(score, 1),
        action=action_from_score(score),
        factors={key: round(value, 1) for key, value in factors.items()},
        weakest_factor=weakest,
        strongest_factor=strongest,
    )


def score_ticker(item: TickerSnapshot) -> float:
    momentum = mean([
        linear_score(item.change_5d_pct, -10, 10),
        linear_score(item.change_20d_pct, -20, 20),
    ])
    technical = mean([
        65 if item.above_50dma else 35 if item.above_50dma is False else 50,
        65 if item.above_200dma else 35 if item.above_200dma is False else 50,
        inverse_linear_score(item.rsi_14, 35, 80),
    ])
    volume = linear_score(item.volume_ratio_20d, 0.6, 1.8)
    return round(momentum * 0.50 + technical * 0.30 + volume * 0.20, 1)


def calculate_jensen_score(nvidia: NvidiaSoxOutput) -> JensenScore:
    ticker_scores: dict[str, float] = {}
    weighted_scores: list[float] = []
    category_buckets: dict[str, list[float]] = {}
    risk_flags: list[str] = []

    for item in nvidia.jensen_universe:
        score = score_ticker(item)
        ticker_scores[item.ticker] = score
        weighted_scores.extend([score] * item.tier_weight)
        category_buckets.setdefault(item.category, []).append(score)
        if item.ticker in {"CRWV", "NBIS"} and score >= 65:
            risk_flags.append(f"{item.ticker}: 엔비디아 순환투자 노출, AI 수요 둔화 시 우선 점검")

    total = round(mean(weighted_scores), 1) if weighted_scores else 50.0
    category_scores = {category: round(mean(scores), 1) for category, scores in category_buckets.items()}
    top_ideas = [
        ticker for ticker, _score in sorted(ticker_scores.items(), key=lambda pair: pair[1], reverse=True)[:3]
    ]
    return JensenScore(
        score=total,
        category_scores=category_scores,
        ticker_scores=ticker_scores,
        top_ideas=top_ideas,
        risk_flags=risk_flags,
    )
