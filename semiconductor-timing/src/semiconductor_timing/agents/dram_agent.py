from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from semiconductor_timing.agents.base import BaseAgent
from semiconductor_timing.config import get_settings
from semiconductor_timing.schemas import AgentMeta, DramHbmOutput


PRICE_URL = "https://www.trendforce.com/price"
NEWS_QUERIES = [
    "TrendForce DDR5 contract price HBM supply",
    "DRAMeXchange DDR5 spot price HBM tight supply",
    "TrendForce HBM3E SK hynix Samsung Micron supply",
]

POSITIVE_WORDS = [
    "tight",
    "shortage",
    "surge",
    "rise",
    "up",
    "increase",
    "strong",
    "bullish",
    "타이트",
    "부족",
    "급등",
    "상승",
    "강세",
]
NEGATIVE_WORDS = [
    "oversupply",
    "fall",
    "drop",
    "decline",
    "weak",
    "cut",
    "down",
    "과잉",
    "하락",
    "약세",
    "둔화",
]


def parse_float(text: str) -> float | None:
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text.replace(",", ""))
    return float(match.group(0)) if match else None


def fetch_trendforce_price() -> tuple[float | None, float | None, str | None]:
    response = requests.get(
        PRICE_URL,
        headers={"User-Agent": "semiconductor-timing/0.1"},
        timeout=20,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for tr in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
        if not cells:
            continue
        product = cells[0].lower()
        if "ddr5 16gb" in product and "ett" not in product:
            numeric_cells = [parse_float(cell) for cell in cells[1:]]
            numeric_cells = [value for value in numeric_cells if value is not None]
            price = numeric_cells[4] if len(numeric_cells) >= 5 else (numeric_cells[-1] if numeric_cells else None)
            change = None
            for cell in reversed(cells):
                if "%" in cell:
                    change = parse_float(cell)
                    if change is not None and "▼" in cell and change > 0:
                        change *= -1
                    break
            return price, change, PRICE_URL

    text = " ".join(soup.get_text(" ").split())

    # Public TrendForce page can render as text such as:
    # DDR5 16Gb (2Gx8) 4800/5600 ... 38.50 ▲ 2.12 %
    row_match = re.search(
        r"(DDR5\s+16Gb.*?)(?:DDR4|NAND|Flash|$)",
        text,
        flags=re.IGNORECASE,
    )
    if not row_match:
        return None, None, PRICE_URL

    row = row_match.group(1)
    numbers = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", row)]
    price = None
    if numbers:
        # The last non-percent number on the public row is often the average spot price.
        candidates = [value for value in numbers if value > 0.1]
        price = candidates[-2] if len(candidates) >= 2 else candidates[-1]

    change = None
    change_match = re.search(r"([▲▼+-]?)\s*(\d+(?:\.\d+)?)\s*%", row)
    if change_match:
        sign = -1 if change_match.group(1) == "▼" else 1
        change = sign * float(change_match.group(2))

    return price, change, PRICE_URL


def fetch_google_news(query: str, limit: int = 5) -> list[dict]:
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    )
    response = requests.get(url, timeout=20, headers={"User-Agent": "semiconductor-timing/0.1"})
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items = []
    for item in root.findall("./channel/item")[:limit]:
        title = item.findtext("title", default="").strip()
        link = item.findtext("link", default="").strip()
        if title:
            items.append({"title": title, "link": link})
    return items


def score_sentiment(headlines: list[str]) -> float:
    if not headlines:
        return 0.0
    text = " ".join(headlines).lower()
    pos = sum(text.count(word.lower()) for word in POSITIVE_WORDS)
    neg = sum(text.count(word.lower()) for word in NEGATIVE_WORDS)
    total = pos + neg
    if total == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / total))


def trend_from_sentiment(sentiment: float, spot_change: float | None) -> str:
    if spot_change is not None:
        if spot_change >= 1:
            return "상승"
        if spot_change <= -1:
            return "하락"
    if sentiment >= 0.25:
        return "상승"
    if sentiment <= -0.25:
        return "하락"
    return "보합"


def hbm_supply_from_sentiment(sentiment: float) -> int:
    if sentiment >= 0.6:
        return 4
    if sentiment >= 0.25:
        return 3
    if sentiment > -0.25:
        return 2
    if sentiment > -0.6:
        return 1
    return 0


class DramAgent(BaseAgent):
    name = "dram_hbm"

    def run(self) -> DramHbmOutput:
        settings = get_settings()
        fallback_count = 0
        source_urls: list[str] = []
        headlines: list[str] = []
        spot_price = None
        spot_change = None

        try:
            spot_price, spot_change, url = fetch_trendforce_price()
            if url:
                source_urls.append(url)
            if spot_price is None and spot_change is None:
                fallback_count += 1
        except requests.RequestException:
            fallback_count += 1

        for query in NEWS_QUERIES:
            try:
                for item in fetch_google_news(query):
                    if item["title"] not in headlines:
                        headlines.append(item["title"])
                    if item["link"] and item["link"] not in source_urls:
                        source_urls.append(item["link"])
            except (requests.RequestException, ET.ParseError):
                fallback_count += 1

        sentiment = score_sentiment(headlines)
        contract_trend = trend_from_sentiment(sentiment, spot_change)
        confidence = 0.85
        if spot_price is None:
            confidence -= 0.25
        if not headlines:
            confidence -= 0.25
        confidence -= min(0.25, fallback_count * 0.05)
        confidence = max(0.3, min(0.9, confidence))

        return DramHbmOutput(
            meta=AgentMeta(
                agent=self.name,
                confidence=confidence,
                fallback_used=fallback_count > 0 or spot_price is None,
                timestamp=datetime.now(ZoneInfo(settings.timezone)),
            ),
            ddr5_spot_price_usd=spot_price,
            ddr5_spot_change_pct=spot_change,
            ddr5_contract_trend=contract_trend,
            hbm_supply_status=hbm_supply_from_sentiment(sentiment),
            hbm_keywords_sentiment=round(sentiment, 2),
            inventory_weeks=None,
            headlines=headlines[:8],
            source_urls=source_urls[:8],
        )
