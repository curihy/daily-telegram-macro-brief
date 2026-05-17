from __future__ import annotations

import html
import os
import sys
import traceback
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import quote_plus
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
    MarketTicker("^SOX", "SOX"),
    MarketTicker("SOXX", "SOXX ETF"),
    MarketTicker("SMH", "SMH ETF"),
    MarketTicker("NVDA", "Nvidia"),
    MarketTicker("AMD", "AMD"),
    MarketTicker("AVGO", "Broadcom"),
    MarketTicker("MU", "Micron"),
    MarketTicker("TSM", "TSMC ADR"),
    MarketTicker("ASML", "ASML ADR"),
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
    MarketTicker("005930.KS", "Samsung Electronics"),
    MarketTicker("000660.KS", "SK Hynix"),
    MarketTicker("091160.KS", "KODEX Semiconductor"),
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

NEWS_QUERIES = [
    "Nvidia AI data center capex semiconductor",
    "SK Hynix HBM Samsung Electronics semiconductor",
    "TSMC ASML Micron AI semiconductor",
    "US China semiconductor export controls",
    "Korea semiconductor stocks foreign investors",
    "war oil Middle East market risk",
    "AI investment Microsoft Meta Google Amazon capex",
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


def fetch_news_rss(query: str, limit: int = 4) -> list[dict]:
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=ko&gl=KR&ceid=KR:ko"
    )
    response = requests.get(
        url,
        timeout=20,
        headers={"User-Agent": "daily-macro-brief/1.0"},
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items = []
    for item in root.findall("./channel/item")[:limit]:
        title = item.findtext("title", default="").strip()
        link = item.findtext("link", default="").strip()
        source = item.findtext("source", default="").strip()
        published = item.findtext("pubDate", default="").strip()
        if title:
            items.append(
                {
                    "query": query,
                    "title": title,
                    "source": source,
                    "published": published,
                    "link": link,
                }
            )
    return items


def fetch_news_snapshot() -> list[dict]:
    seen: set[str] = set()
    news: list[dict] = []
    for query in NEWS_QUERIES:
        try:
            for item in fetch_news_rss(query):
                key = item["title"].lower()
                if key in seen:
                    continue
                seen.add(key)
                news.append(item)
        except (requests.RequestException, ET.ParseError):
            continue
    return news[:24]


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


def find_market_row(market: pd.DataFrame, label: str) -> dict | None:
    matched = market.loc[market["label"] == label]
    if matched.empty:
        return None
    return matched.iloc[0].to_dict()


def summarize_market_context(market: pd.DataFrame, rates: list[dict]) -> str:
    labels = [
        "Nasdaq 100",
        "SOX",
        "SOXX ETF",
        "SMH ETF",
        "Nvidia",
        "AMD",
        "Broadcom",
        "Micron",
        "TSMC ADR",
        "ASML ADR",
        "Samsung Electronics",
        "SK Hynix",
        "KODEX Semiconductor",
        "VIX",
        "DXY",
        "USD/KRW",
        "WTI",
        "Gold",
        "KOSPI",
        "KOSDAQ",
        "Nikkei 225",
        "Hang Seng",
    ]
    lines = []
    for label in labels:
        row = find_market_row(market, label)
        if not row:
            continue
        lines.append(
            f"{label}: latest {compact_number(row['latest'])}, "
            f"1D {pct(row['day_change'])}, 5D {pct(row['week_change'])}"
        )
    for row in rates:
        lines.append(f"{row['label']}: {row['latest']:.2f}{row['suffix']}, {bp(row['change_bp'])}")
    return "\n".join(lines)


def summarize_news_context(news: list[dict]) -> str:
    lines = []
    for item in news[:20]:
        source = f" ({item['source']})" if item.get("source") else ""
        lines.append(f"- {item['title']}{source}")
    return "\n".join(lines)


def call_openrouter(market: pd.DataFrame, rates: list[dict], news: list[dict]) -> str | None:
    api_key = env("OPENROUTER_API_KEY")
    if not api_key or api_key == "replace_me":
        return None

    model = env("OPENROUTER_MODEL", "openrouter/auto")
    today = datetime.now(ZoneInfo(env("TIMEZONE", "Asia/Seoul"))).strftime("%Y-%m-%d")
    prompt = f"""
오늘 날짜: {today}
목표: 한국장 개장 전 삼성전자, SK하이닉스, 반도체 소부장 ETF 관점의 bold한 투자 판단.
제약:
- 한국어로 작성.
- 전체 항목은 정확히 10개.
- 각 항목은 제목 1줄 + 세부 내용 최대 3줄.
- 숫자 중심, 짧고 단호하게.
- 오늘 전망, 이번주 전망, 한 달 전망, AI 혁명이 주식 관점에서 어디까지 왔는지 반드시 포함.
- 장기금리, 전쟁/유가, 중국 규제, 아시아 상대우위, 빅테크 AI 투자 동향을 반드시 반영.
- 최종 판단은 '매수 우위', '보유', '관망', '일부 차익실현', '방어' 중 하나 이상을 명시.
- 확실하지 않은 뉴스는 단정하지 말고 '확인 필요'라고 써라.

[시장 데이터]
{summarize_market_context(market, rates)}

[무료 뉴스/RSS 헤드라인]
{summarize_news_context(news)}
""".strip()

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": env("OPENROUTER_SITE_URL", "https://github.com/curihy/daily-telegram-macro-brief"),
            "X-Title": env("OPENROUTER_APP_NAME", "Daily Korean Semiconductor Brief"),
        },
        json={
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a concise Korean market strategist. "
                        "You synthesize market data and news into bold but caveated investment views."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 1400,
        },
        timeout=45,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"].strip()


def call_ollama(market: pd.DataFrame, rates: list[dict], news: list[dict]) -> str | None:
    model = env("OLLAMA_MODEL")
    if not model:
        return None

    host = env("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    today = datetime.now(ZoneInfo(env("TIMEZONE", "Asia/Seoul"))).strftime("%Y-%m-%d")
    prompt = f"""
오늘 날짜: {today}
목표: 한국장 개장 전 삼성전자, SK하이닉스, 반도체 소부장 ETF 관점의 bold한 투자 판단.
제약:
- 한국어로 작성.
- 전체 항목은 정확히 10개.
- 각 항목은 제목 1줄 + 세부 내용 최대 3줄.
- 숫자 중심, 짧고 단호하게.
- 오늘 전망, 이번주 전망, 한 달 전망, AI 혁명이 주식 관점에서 어디까지 왔는지 반드시 포함.
- 장기금리, 전쟁/유가, 중국 규제, 아시아 상대우위, 빅테크 AI 투자 동향을 반드시 반영.
- 최종 판단은 '매수 우위', '보유', '관망', '일부 차익실현', '방어' 중 하나 이상을 명시.
- 확실하지 않은 뉴스는 단정하지 말고 '확인 필요'라고 써라.
- 사고 과정은 출력하지 말고 최종 리포트만 출력하라. /no_think

[시장 데이터]
{summarize_market_context(market, rates)}

[무료 뉴스/RSS 헤드라인]
{summarize_news_context(news)}
""".strip()

    response = requests.post(
        f"{host}/api/chat",
        json={
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a concise Korean market strategist. "
                        "Return only the final report, not hidden reasoning."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": int(env("OLLAMA_NUM_CTX", "16384")),
            },
        },
        timeout=int(env("OLLAMA_TIMEOUT", "300")),
    )
    response.raise_for_status()
    return response.json()["message"]["content"].strip()


def format_fallback_semiconductor_report(market: pd.DataFrame, rates: list[dict], news: list[dict]) -> str:
    tz_name = env("TIMEZONE", "Asia/Seoul")
    now = datetime.now(ZoneInfo(tz_name))
    regime, notes = build_regime(market, rates)
    sox = get_change(market, "SOX")
    nvda = get_change(market, "Nvidia")
    hynix = get_change(market, "SK Hynix")
    samsung = get_change(market, "Samsung Electronics")
    krw = get_change(market, "USD/KRW")
    vix = get_change(market, "VIX")
    ten_year = next((row for row in rates if row["label"] == "US 10Y"), None)
    ten_year_change = ten_year["change_bp"] if ten_year else None

    score = 0
    for value in [sox, nvda, hynix]:
        if value is not None:
            score += 1 if value > 1 else -1 if value < -1 else 0
    if ten_year_change is not None:
        score += -1 if ten_year_change > 5 else 1 if ten_year_change < -5 else 0
    if krw is not None:
        score += -1 if krw > 0.4 else 1 if krw < -0.4 else 0
    if vix is not None:
        score += -1 if vix > 5 else 1 if vix < -5 else 0

    if score >= 3:
        call = "매수 우위"
        today_view = "강세"
    elif score >= 1:
        call = "보유"
        today_view = "강보합"
    elif score <= -3:
        call = "방어"
        today_view = "약세"
    elif score <= -1:
        call = "일부 차익실현"
        today_view = "혼조"
    else:
        call = "관망"
        today_view = "중립"

    top_news = [item["title"] for item in news[:5]]
    news_line = " / ".join(top_news[:2]) if top_news else "무료 RSS에서 핵심 뉴스 확인 제한"

    lines = [
        f"<b>AI 반도체 6AM</b> {now:%Y-%m-%d}",
        f"1. 최종 판단: <b>{html.escape(call)}</b>",
        f"   오늘 {today_view}, 시장 톤 {regime}. SOX {pct(sox)}, Nvidia {pct(nvda)}.",
        f"2. 한국 대장주: 삼성전자 {pct(samsung)}, SK하이닉스 {pct(hynix)}.",
        "   HBM/AI 노출도가 큰 하이닉스 우위, 삼성은 메모리/파운드리 뉴스 확인.",
        f"3. 소부장 ETF 관점: SOXX {pct(get_change(market, 'SOXX ETF'))}, SMH {pct(get_change(market, 'SMH ETF'))}.",
        "   갭상승 추격보다 SOX와 환율이 동시에 우호적일 때 눌림 매수 우선.",
        f"4. 금리 브레이크: US 10Y {bp(ten_year_change)}.",
        "   10Y 급등은 AI 장기 성장주의 밸류에이션을 바로 누르는 변수.",
        f"5. 환율/수급: USD/KRW {pct(krw)}, DXY {pct(get_change(market, 'DXY'))}.",
        "   원화 약세가 커지면 외국인 한국 반도체 수급은 방어적으로 해석.",
        f"6. 위험지표: VIX {pct(vix)}, WTI {pct(get_change(market, 'WTI'))}.",
        "   전쟁/유가 급등은 인플레와 금리 재상승 경로로 반도체에 부정적.",
        "7. 중국 규제: 신규 악재는 뉴스 헤드라인으로 확인 필요.",
        "   대중 수출규제 강화는 장비/AI칩 체인에 즉시 할인 요인.",
        "8. 아시아 상대우위: 한국은 HBM, 대만은 파운드리, 일본은 장비/소재.",
        "   AI 서버 수요가 유지되면 한국은 메모리 사이클에서 상대 매력 유지.",
        f"9. AI 사이클 위치: 인프라 CAPEX 확장 국면.",
        f"   최신 뉴스: {html.escape(news_line[:180])}",
        f"10. 이번주/1개월: {call} 유지, 단 금리+환율+Nvidia 동반 악화 시 방어.",
        "   AI 혁명은 아직 실적 검증 전반부지만 단기 주가는 과열을 반복할 수 있음.",
    ]
    return "\n".join(lines)


def format_report(market: pd.DataFrame, rates: list[dict], news: list[dict]) -> str:
    if market.empty:
        raise RuntimeError("No market data was downloaded.")

    local_report = call_ollama(market, rates, news)
    if local_report:
        return html.escape(local_report).replace("\n", "\n")

    llm_report = call_openrouter(market, rates, news)
    if llm_report:
        return html.escape(llm_report).replace("\n", "\n")
    return format_fallback_semiconductor_report(market, rates, news)


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
    if response.status_code == 404:
        raise ConfigError(
            "Telegram API returned 404. Check TELEGRAM_BOT_TOKEN. "
            "It should look like 123456789:ABCDEF..., without 'bot' prefix, quotes, or spaces."
        )
    if response.status_code == 400:
        raise ConfigError(
            "Telegram API returned 400. Check TELEGRAM_CHAT_ID and make sure the bot is an admin "
            "with permission to post in the channel."
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
        news = fetch_news_snapshot()
        report = format_report(market, rates, news)
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
