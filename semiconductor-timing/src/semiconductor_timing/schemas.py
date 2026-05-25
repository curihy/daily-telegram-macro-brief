from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class AgentMeta(BaseModel):
    agent: str
    confidence: float = Field(ge=0, le=1)
    fallback_used: bool = False
    timestamp: datetime


class TickerSnapshot(BaseModel):
    ticker: str
    name: str
    category: str = ""
    tier_weight: int = 1
    close: Optional[float] = None
    change_1d_pct: Optional[float] = None
    change_5d_pct: Optional[float] = None
    change_20d_pct: Optional[float] = None
    rsi_14: Optional[float] = None
    above_50dma: Optional[bool] = None
    above_200dma: Optional[bool] = None
    volume_ratio_20d: Optional[float] = None
    score: Optional[float] = None


class NvidiaSoxOutput(BaseModel):
    meta: AgentMeta
    nvda: Optional[TickerSnapshot]
    sox: Optional[TickerSnapshot]
    semiconductor_etfs: List[TickerSnapshot]
    jensen_universe: List[TickerSnapshot]


class MacroOutput(BaseModel):
    meta: AgentMeta
    us_10y_yield: Optional[float] = None
    us_2y_yield: Optional[float] = None
    yield_curve_spread: Optional[float] = None
    us_10y_change_bp: Optional[float] = None
    dxy: Optional[float] = None
    dxy_change_pct: Optional[float] = None
    usd_krw: Optional[float] = None
    usd_krw_change_pct: Optional[float] = None
    vix: Optional[float] = None
    vix_change_pct: Optional[float] = None


class DramHbmOutput(BaseModel):
    meta: AgentMeta
    ddr5_spot_price_usd: Optional[float] = None
    ddr5_spot_change_pct: Optional[float] = None
    ddr5_contract_trend: str = "확인 필요"
    hbm_supply_status: Optional[int] = Field(default=None, ge=0, le=4)
    hbm_keywords_sentiment: Optional[float] = Field(default=None, ge=-1, le=1)
    inventory_weeks: Optional[float] = None
    headlines: List[str] = []
    source_urls: List[str] = []


class FlowOutput(BaseModel):
    meta: AgentMeta
    samsung_foreign_net_buy_billion: Optional[float] = None
    hynix_foreign_net_buy_billion: Optional[float] = None
    samsung_inst_net_buy_billion: Optional[float] = None
    hynix_inst_net_buy_billion: Optional[float] = None
    kospi_foreign_net_buy_billion: Optional[float] = None
    foreign_4week_trend_score: Optional[int] = Field(default=None, ge=0, le=4)
    samsung_short_ratio_pct: Optional[float] = None
    hynix_short_ratio_pct: Optional[float] = None
    samsung_close: Optional[float] = None
    hynix_close: Optional[float] = None
    samsung_pbr: Optional[float] = None
    hynix_pbr: Optional[float] = None


class BrokerTarget(BaseModel):
    provider: str
    analyst: Optional[str] = None
    report_date: Optional[str] = None
    target_price: Optional[int] = None
    previous_target_price: Optional[int] = None
    change_pct: Optional[float] = None
    opinion: Optional[str] = None


class StockConsensus(BaseModel):
    ticker: str
    name: str
    consensus_date: Optional[str] = None
    opinion_score: Optional[float] = None
    average_target_price: Optional[int] = None
    estimated_institutions: Optional[int] = None
    top_targets: List[BrokerTarget] = []


class ConsensusOutput(BaseModel):
    meta: AgentMeta
    stocks: List[StockConsensus] = []
    source_urls: List[str] = []


class MainScore(BaseModel):
    score: float = Field(ge=0, le=100)
    action: str
    factors: Dict[str, float]
    weakest_factor: Optional[str] = None
    strongest_factor: Optional[str] = None


class JensenScore(BaseModel):
    score: float = Field(ge=0, le=100)
    category_scores: Dict[str, float]
    ticker_scores: Dict[str, float]
    top_ideas: List[str]
    risk_flags: List[str]


class ValidationPass(BaseModel):
    name: str
    passed: bool
    warnings: List[str] = []
    errors: List[str] = []


class ValidationSummary(BaseModel):
    grade: Literal["A", "B", "C", "D"]
    passes: List[ValidationPass]
    warnings: List[str] = []


class DailyResult(BaseModel):
    run_at: datetime
    dram: DramHbmOutput
    nvidia: NvidiaSoxOutput
    macro: MacroOutput
    flow: FlowOutput
    consensus: ConsensusOutput
    main_score: MainScore
    jensen_score: JensenScore
    validation: ValidationSummary
    report_text: str
