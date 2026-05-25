from __future__ import annotations

from datetime import datetime

from semiconductor_timing.schemas import DailyResult


JENSEN_CATEGORY_ORDER = ["포토닉스", "네트워킹", "클라우드", "설계도구", "제조", "AI서버", "연결성", "모바일칩", "산업자동화", "모빌리티"]
DIVIDER = "━━━━━━━━━━━━"


def pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.2f}%"


def bp(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+.0f}bp"


def won(value: int | float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.0f}원"


def score_signal(score: float | None) -> str:
    if score is None:
        return "⚪"
    if score >= 70:
        return "🟢"
    if score >= 45:
        return "🟡"
    return "🔴"


def trend_signal(value: float | None, reverse: bool = False) -> str:
    if value is None:
        return "⚪"
    positive = value > 0
    negative = value < 0
    if reverse:
        positive, negative = negative, positive
    if positive:
        return "🟢"
    if negative:
        return "🔴"
    return "🟡"


def risk_signal(text: str | None) -> str:
    if not text or text == "없음":
        return "🟢"
    return "🔴"


def consensus_by_ticker(result: DailyResult, ticker: str):
    return next((stock for stock in result.consensus.stocks if stock.ticker == ticker), None)


def consensus_summary_line(stock) -> str:
    if not stock:
        return "컨센서스 n/a."
    date = stock.consensus_date or "기준일 n/a"
    opinion = f"{stock.opinion_score:.2f}" if stock.opinion_score is not None else "n/a"
    institutions = stock.estimated_institutions if stock.estimated_institutions is not None else "n/a"
    return f"{stock.name} 평균 목표가 {won(stock.average_target_price)} ({date}, 의견 {opinion}, {institutions}개 기관)."


def top_targets_line(stock) -> str:
    if not stock or not stock.top_targets:
        return "Top5 목표가 n/a."
    items = []
    for target in stock.top_targets[:5]:
        analyst = target.analyst or "담당자 미공개"
        date = target.report_date or "일자 n/a"
        items.append(f"{target.provider}/{analyst} {won(target.target_price)}({date})")
    return "Top5 " + "; ".join(items) + "."


def holder_action(score: float) -> str:
    if score >= 75:
        return "보유 유지 + 눌림 추가"
    if score >= 60:
        return "보유 유지"
    if score >= 40:
        return "보유하되 추격 금지"
    if score >= 25:
        return "일부 차익실현"
    return "방어·현금화 우선"


def new_entry_action(score: float) -> str:
    if score >= 75:
        return "분할 진입 가능"
    if score >= 60:
        return "소액 선진입만"
    if score >= 40:
        return "관망"
    if score >= 25:
        return "신규 진입 보류"
    return "진입 금지"


def stance_reason(score: float, weakest: str | None) -> str:
    if score >= 75:
        return "메인 점수가 강한 매수권이라 랠리 지속 확률이 높습니다."
    if score >= 60:
        return "우호 팩터가 더 많지만 단기 과열과 변동성은 열어둡니다."
    if score >= 40:
        return f"점수가 중립권이라 {weakest or '최약 팩터'} 개선 확인이 필요합니다."
    if score >= 25:
        return f"{weakest or '최약 팩터'} 부담이 커서 리스크 관리가 우선입니다."
    return "복수 핵심 팩터가 약해 손실 방어가 우선인 구간입니다."


def numbered_item(number: int, title: str, *details: str, icon: str = "🔎") -> list[str]:
    lines = ["", f"{number}. {icon} {title}"]
    clean_details = [detail for detail in details if detail]
    for detail in clean_details[:5]:
        lines.append(f"   ▸ {detail}")
    return lines


def headline_item(title: str, *details: str) -> list[str]:
    lines = [DIVIDER, f"🚦 {title}"]
    for detail in [detail for detail in details if detail][:5]:
        lines.append(f"   ▸ {detail}")
    lines.append(DIVIDER)
    return lines


def jensen_category_lines(result: DailyResult) -> list[str]:
    buckets: dict[str, list[tuple[str, float]]] = {}
    for ticker, score in result.jensen_score.ticker_scores.items():
        item = next((candidate for candidate in result.nvidia.jensen_universe if candidate.ticker == ticker), None)
        if not item:
            continue
        buckets.setdefault(item.category, []).append((ticker, score))

    lines: list[str] = []
    for category in JENSEN_CATEGORY_ORDER:
        scores = buckets.get(category)
        if not scores:
            continue
        avg = result.jensen_score.category_scores.get(category, 50)
        members = ", ".join(f"{ticker} {score:.0f}" for ticker, score in sorted(scores, key=lambda pair: pair[1], reverse=True))
        lines.append(f"   {score_signal(avg)} {category}: {avg:.0f}점 | {members}")

    if not lines:
        lines.append("   ⚪ 데이터 부족: 젠슨 유니버스 카테고리 점수 산출 불가")

    while len(lines) < 10:
        if len(lines) == 1:
            lines.append("   🟢 해석: 60점 이상 카테고리는 AI CAPEX 확산 수혜 후보로 봅니다.")
        elif len(lines) == 2:
            lines.append("   🟡 해석: 45~59점 카테고리는 방향 확인 전 관망 구간입니다.")
        elif len(lines) == 3:
            lines.append("   🔴 해석: 45점 미만 카테고리는 랠리 지속성에 부담을 줍니다.")
        elif len(lines) == 4:
            lines.append("   🟢 연결: 포토닉스·네트워킹 강세는 HBM/AI 서버 체인에 우호적입니다.")
        elif len(lines) == 5:
            lines.append("   🟡 연결: 클라우드 강세는 GPU 수요 지속 신호지만 순환투자 리스크도 봅니다.")
        elif len(lines) == 6:
            lines.append("   🟢 연결: 설계도구 강세는 AI 반도체 개발 사이클 확장 신호입니다.")
        elif len(lines) == 7:
            lines.append("   🟡 연결: 제조 약세는 공급망 병목 또는 파운드리 불확실성을 뜻할 수 있습니다.")
        elif len(lines) == 8:
            lines.append("   🟢 한국 연결: 유니버스 강세가 유지되면 SK하이닉스/HBM 체인 우위입니다.")
        else:
            lines.append("   🟡 결론: 유니버스가 60점 위로 올라서야 한국 반도체 랠리 신뢰도가 커집니다.")
    return lines[:10]


def render_report(result: DailyResult) -> str:
    dram = result.dram
    flow = result.flow
    nvda = result.nvidia.nvda
    sox = result.nvidia.sox
    macro = result.macro
    samsung_consensus = consensus_by_ticker(result, "005930")
    hynix_consensus = consensus_by_ticker(result, "000660")
    main = result.main_score
    jensen = result.jensen_score
    validation = result.validation
    top = ", ".join(jensen.top_ideas) if jensen.top_ideas else "n/a"
    warnings = " / ".join(validation.warnings[:2]) if validation.warnings else "없음"
    risk_line = " / ".join(jensen.risk_flags[:2]) if jensen.risk_flags else warnings
    holder = holder_action(main.score)
    new_entry = new_entry_action(main.score)
    reason = stance_reason(main.score, main.weakest_factor)
    category_lines = jensen_category_lines(result)

    main_icon = score_signal(main.score)
    jensen_icon = score_signal(jensen.score)
    dram_icon = score_signal((dram.hbm_supply_status or 0) * 25)
    flow_icon = score_signal((flow.foreign_4week_trend_score or 0) * 25)
    macro_icon = "🟢" if (macro.us_10y_change_bp or 0) <= 5 and (macro.usd_krw_change_pct or 0) <= 0.5 else "🟡"

    lines = [
        f"📌 반도체 타이밍 MVP | {datetime.now().strftime('%Y-%m-%d')}",
        f"{main_icon} 메인 {main.score}/100  |  {jensen_icon} 유니버스 {jensen.score}/100  |  신뢰도 {validation.grade}",
        f"{dram_icon} D램/HBM  {flow_icon} 외인수급  {macro_icon} 매크로  {risk_signal(risk_line)} 리스크",
    ]
    lines.extend(headline_item(
        "종합판단",
        f"{main_icon} 기존 보유자: {holder}.",
        f"{main_icon} 신규 진입자: {new_entry}.",
        f"{jensen_icon} 메인 {main.score}/100, 유니버스 {jensen.score}/100, 신뢰도 {validation.grade}.",
        f"🧭 {reason}",
        f"🟢 최강 {main.strongest_factor} / 🔴 최약 {main.weakest_factor}, D램 추세 {dram.ddr5_contract_trend}.",
    ))
    lines.extend(numbered_item(
        1,
        "포지션 전략",
        "갭상승 추격보다 점수와 최약 팩터 개선을 먼저 확인합니다.",
        "60점 미만이면 첫 매수보다 관찰 리스트 유지가 기본입니다.",
        f"진입한다면 리스크 기준은 '{main.weakest_factor or '최약 팩터'}'입니다.",
        "기존 보유자는 급락 신호가 아니라면 전량 매도보다 비중 조절이 우선입니다.",
        "신규 진입자는 60점 회복 또는 최약 팩터 개선 전까지 대기 전략이 낫습니다.",
        icon=main_icon,
    ))
    lines.extend(numbered_item(
        2,
        "D램/HBM 가격",
        f"{trend_signal(dram.ddr5_spot_change_pct)} DDR5 현물가 {dram.ddr5_spot_price_usd or 'n/a'}, 변동률 {pct(dram.ddr5_spot_change_pct)}.",
        f"{dram_icon} 계약가 추세는 {dram.ddr5_contract_trend}, HBM 공급 타이트 점수는 {dram.hbm_supply_status if dram.hbm_supply_status is not None else 'n/a'}/4입니다.",
        f"{trend_signal(dram.hbm_keywords_sentiment)} 뉴스 감성은 {dram.hbm_keywords_sentiment if dram.hbm_keywords_sentiment is not None else 'n/a'}, confidence {dram.meta.confidence:.2f}입니다.",
        "DDR5/HBM이 동시에 우호적이면 SK하이닉스와 후공정 소부장 선별 강도가 올라갑니다.",
        "공개 가격 수집은 제한적이라 가격값이 n/a이면 뉴스 기반 추세를 보조 신호로만 씁니다.",
        icon=dram_icon,
    ))
    lines.extend(numbered_item(
        3,
        "KRX 수급/밸류",
        f"{trend_signal(flow.samsung_foreign_net_buy_billion)} 삼성 외인 {flow.samsung_foreign_net_buy_billion if flow.samsung_foreign_net_buy_billion is not None else 'n/a'}억원, 기관 {flow.samsung_inst_net_buy_billion if flow.samsung_inst_net_buy_billion is not None else 'n/a'}억원.",
        f"{trend_signal(flow.hynix_foreign_net_buy_billion)} 하이닉스 외인 {flow.hynix_foreign_net_buy_billion if flow.hynix_foreign_net_buy_billion is not None else 'n/a'}억원, 기관 {flow.hynix_inst_net_buy_billion if flow.hynix_inst_net_buy_billion is not None else 'n/a'}억원.",
        f"{flow_icon} 코스피 외인 {flow.kospi_foreign_net_buy_billion if flow.kospi_foreign_net_buy_billion is not None else 'n/a'}억원, 4주 수급 점수 {flow.foreign_4week_trend_score if flow.foreign_4week_trend_score is not None else 'n/a'}/4.",
        f"삼성 PBR {flow.samsung_pbr if flow.samsung_pbr is not None else 'n/a'}, 하이닉스 PBR {flow.hynix_pbr if flow.hynix_pbr is not None else 'n/a'}.",
        f"공매도 비중은 삼성 {flow.samsung_short_ratio_pct if flow.samsung_short_ratio_pct is not None else 'n/a'}%, 하이닉스 {flow.hynix_short_ratio_pct if flow.hynix_short_ratio_pct is not None else 'n/a'}%입니다.",
        icon=flow_icon,
    ))
    lines.extend(numbered_item(
        4,
        "증권사 컨센서스",
        f"🧾 {consensus_summary_line(samsung_consensus)}",
        f"🏆 삼성 {top_targets_line(samsung_consensus)}",
        f"🧾 {consensus_summary_line(hynix_consensus)}",
        f"🏆 하이닉스 {top_targets_line(hynix_consensus)}",
        "무료 공개 소스 기준으로 애널리스트 개인명은 미공개인 경우가 많아 증권사/담당자 미공개로 표기합니다.",
        icon="🧾",
    ))
    lines.extend(numbered_item(
        5,
        "미국 선행지표",
        f"{trend_signal(nvda.change_5d_pct if nvda else None)} NVDA 5D {pct(nvda.change_5d_pct if nvda else None)}, {trend_signal(sox.change_5d_pct if sox else None)} SOX 5D {pct(sox.change_5d_pct if sox else None)}.",
        "NVDA와 SOX가 같이 강해야 한국 반도체 랠리 지속성이 높아집니다.",
        "둘 중 하나가 약하면 삼성전자보다 SK하이닉스/HBM 체인의 선별 접근이 낫습니다.",
        "SOX가 강하고 NVDA가 약하면 섹터 확산은 있지만 AI 대장주 신뢰도는 낮습니다.",
        "NVDA가 반등하면 한국 반도체는 장중 심리 회복 속도가 빨라질 수 있습니다.",
        icon=jensen_icon,
    ))
    lines.extend(numbered_item(
        6,
        "매크로 브레이크",
        f"{trend_signal(macro.us_10y_change_bp, reverse=True)} 10Y {bp(macro.us_10y_change_bp)}, {trend_signal(macro.usd_krw_change_pct, reverse=True)} USD/KRW {pct(macro.usd_krw_change_pct)}, {trend_signal(macro.vix_change_pct, reverse=True)} VIX {pct(macro.vix_change_pct)}.",
        "금리와 원/달러가 동시에 오르면 외국인 수급과 밸류에이션에 부담입니다.",
        "반대로 금리 안정과 원화 안정이 같이 나오면 반도체 랠리 신뢰도가 올라갑니다.",
        "VIX가 안정되어도 환율이 오르면 한국장에서는 수급 부담이 먼저 반영됩니다.",
        "10Y가 급등하면 AI 성장주의 장기 현금흐름 할인율 부담이 커집니다.",
        icon=macro_icon,
    ))
    lines.extend(["", f"7. {jensen_icon} 젠슨 유니버스 카테고리별 10줄"])
    lines.extend(category_lines)
    lines.extend(numbered_item(
        8,
        "리스크 체크",
        f"{risk_signal(risk_line)} {risk_line}",
        "리스크가 가격 강세보다 커지면 보유자는 비중 관리, 신규자는 진입 보류가 우선입니다.",
        "특히 달러/원, 10Y, VIX가 동시에 악화되면 당일 방어 모드로 전환합니다.",
        "순환투자 노출 종목이 강하면 GPU 수요 착시 가능성도 함께 봐야 합니다.",
        "뉴스·공시 이벤트가 나오면 기존 점수보다 장중 가격 반응을 우선합니다.",
        icon=risk_signal(risk_line),
    ))
    lines.extend(numbered_item(
        9,
        "오늘 행동",
        "기존 보유자는 최약 팩터가 악화되지 않는 한 성급한 전량 매도는 피합니다.",
        "신규 진입자는 60점 미만에서 첫 진입을 서두르지 않습니다.",
        "장중에는 환율과 SK하이닉스 상대강도가 점수 판단의 확인 신호입니다.",
        "오전 갭상승은 추격보다 30~60분 수급 확인 후 판단합니다.",
        "약세 출발 후 SOX/NVDA 선물이 버티면 눌림 반등 가능성을 열어둡니다.",
        icon="🧭",
    ))
    lines.extend(numbered_item(
        10,
        "주의",
        "자동 생성 리포트입니다. 투자 판단은 별도 검증이 필요합니다.",
        "점수는 의사결정 보조용이며 손실 가능성을 제거하지 않습니다.",
        "뉴스·공시·장중 수급이 급변하면 리포트 결론도 빠르게 바뀔 수 있습니다.",
        "개별 종목 매매는 포지션 크기와 손절 기준을 먼저 정한 뒤 실행해야 합니다.",
        "특정 수치가 n/a이면 해당 데이터 소스 또는 API 키 상태를 확인해야 합니다.",
        icon="⚠️",
    ))
    headlines = dram.headlines[:5]
    while len(headlines) < 5:
        headlines.append("추가 공개 헤드라인 없음")
    lines.extend(["", "📰 D램/HBM 참고 헤드라인"])
    lines.extend([f"   ▸ {headline}" for headline in headlines])
    return "\n".join(lines)
