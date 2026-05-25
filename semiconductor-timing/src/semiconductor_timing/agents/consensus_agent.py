from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from semiconductor_timing.agents.base import BaseAgent
from semiconductor_timing.config import get_settings
from semiconductor_timing.schemas import AgentMeta, BrokerTarget, ConsensusOutput, StockConsensus


STOCKS = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
}


def parse_int(text: str | None) -> int | None:
    if not text:
        return None
    value = text.replace(",", "").replace("원", "").strip()
    if not value or value in {"-", "N/A"}:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def parse_float(text: str | None) -> float | None:
    if not text:
        return None
    value = text.replace(",", "").replace("%", "").strip()
    if not value or value in {"-", "N/A"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def fetch_wisereport_html(code: str) -> tuple[str, str]:
    url = f"https://navercomp.wisereport.co.kr/v2/company/c1010001.aspx?cmp_cd={code}"
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"},
        timeout=20,
    )
    response.raise_for_status()
    return response.text, url


def parse_consensus_date(soup: BeautifulSoup) -> str | None:
    header = soup.find(string=lambda text: text and "[기준:" in text)
    if not header:
        return None
    match = re.search(r"\[기준:([0-9.]+)\]", header)
    return match.group(1) if match else None


def parse_summary(soup: BeautifulSoup) -> tuple[float | None, int | None, int | None]:
    table = soup.find("table", id="cTB15")
    if table is None:
        return None, None, None
    rows = table.find_all("tr")
    if len(rows) < 2:
        return None, None, None
    cells = [clean_text(cell.get_text(" ", strip=True)) for cell in rows[-1].find_all(["td", "th"])]
    if len(cells) < 5:
        return None, None, None
    opinion_score = parse_float(cells[0])
    average_target = parse_int(cells[1])
    institutions = parse_int(cells[4])
    return opinion_score, average_target, institutions


def parse_targets(soup: BeautifulSoup) -> list[BrokerTarget]:
    table = soup.find("table", id="cTB24")
    if table is None:
        return []

    targets: list[BrokerTarget] = []
    for row in table.find_all("tr"):
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
        if len(cells) < 7:
            continue
        target_price = parse_int(cells[2])
        if target_price is None:
            continue
        targets.append(
            BrokerTarget(
                provider=cells[0],
                analyst=None,
                report_date=cells[1],
                target_price=target_price,
                previous_target_price=parse_int(cells[3]),
                change_pct=parse_float(cells[4]),
                opinion=cells[5] or None,
            )
        )
    return sorted(targets, key=lambda item: item.target_price or 0, reverse=True)[:5]


class ConsensusAgent(BaseAgent):
    name = "broker_consensus"

    def run(self) -> ConsensusOutput:
        settings = get_settings()
        now = datetime.now(ZoneInfo(settings.timezone))
        stocks: list[StockConsensus] = []
        urls: list[str] = []
        failures = 0

        for code, name in STOCKS.items():
            try:
                html, url = fetch_wisereport_html(code)
                urls.append(url)
                soup = BeautifulSoup(html, "html.parser")
                opinion_score, average_target, institutions = parse_summary(soup)
                stocks.append(
                    StockConsensus(
                        ticker=code,
                        name=name,
                        consensus_date=parse_consensus_date(soup),
                        opinion_score=opinion_score,
                        average_target_price=average_target,
                        estimated_institutions=institutions,
                        top_targets=parse_targets(soup),
                    )
                )
            except requests.RequestException:
                failures += 1
            except Exception:
                failures += 1

        missing = sum(
            stock.average_target_price is None or len(stock.top_targets) == 0
            for stock in stocks
        )
        confidence = max(0.3, 1 - failures * 0.25 - missing * 0.15)

        return ConsensusOutput(
            meta=AgentMeta(
                agent=self.name,
                confidence=round(confidence, 2),
                fallback_used=failures > 0 or missing > 0,
                timestamp=now,
            ),
            stocks=stocks,
            source_urls=urls,
        )
