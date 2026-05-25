from datetime import datetime, timezone

from semiconductor_timing.schemas import AgentMeta, MacroOutput, NvidiaSoxOutput, TickerSnapshot
from semiconductor_timing.scoring.calculators import calculate_jensen_score, calculate_main_score


def test_main_score_range():
    meta = AgentMeta(agent="test", confidence=1, timestamp=datetime.now(timezone.utc))
    nvda = TickerSnapshot(ticker="NVDA", name="Nvidia", change_5d_pct=5)
    sox = TickerSnapshot(ticker="^SOX", name="SOX", change_5d_pct=3)
    hynix = TickerSnapshot(ticker="000660.KS", name="SK Hynix", change_5d_pct=4)
    nvidia = NvidiaSoxOutput(
        meta=meta,
        nvda=nvda,
        sox=sox,
        semiconductor_etfs=[hynix],
        jensen_universe=[],
    )
    macro = MacroOutput(
        meta=meta,
        us_10y_change_bp=-3,
        usd_krw_change_pct=-0.2,
        vix_change_pct=-2,
    )
    score = calculate_main_score(nvidia, macro)
    assert 0 <= score.score <= 100


def test_jensen_score_range():
    meta = AgentMeta(agent="test", confidence=1, timestamp=datetime.now(timezone.utc))
    universe = [
        TickerSnapshot(
            ticker="MRVL",
            name="Marvell",
            category="네트워킹",
            tier_weight=2,
            change_5d_pct=3,
            change_20d_pct=8,
            rsi_14=55,
            above_50dma=True,
            above_200dma=True,
            volume_ratio_20d=1.2,
        )
    ]
    nvidia = NvidiaSoxOutput(meta=meta, nvda=None, sox=None, semiconductor_etfs=[], jensen_universe=universe)
    score = calculate_jensen_score(nvidia)
    assert 0 <= score.score <= 100
    assert score.top_ideas == ["MRVL"]
