from __future__ import annotations

from semiconductor_timing.schemas import ConsensusOutput, DramHbmOutput, FlowOutput, JensenScore, MacroOutput, MainScore, NvidiaSoxOutput, ValidationPass, ValidationSummary


def pass1_integrity(
    nvidia: NvidiaSoxOutput,
    macro: MacroOutput,
    dram: DramHbmOutput | None = None,
    flow: FlowOutput | None = None,
    consensus: ConsensusOutput | None = None,
) -> ValidationPass:
    warnings: list[str] = []
    errors: list[str] = []

    universe_missing = sum(item.close is None for item in nvidia.jensen_universe)
    if universe_missing > 4:
        errors.append(f"젠슨 유니버스 결측 과다: {universe_missing}개")
    elif universe_missing:
        warnings.append(f"젠슨 유니버스 결측: {universe_missing}개")

    if macro.usd_krw is not None and not 900 <= macro.usd_krw <= 1800:
        errors.append(f"USD/KRW 범위 이탈: {macro.usd_krw}")
    if macro.us_10y_yield is not None and not 0 <= macro.us_10y_yield <= 10:
        errors.append(f"미국 10Y 범위 이탈: {macro.us_10y_yield}")
    if nvidia.meta.confidence < 0.5 or macro.meta.confidence < 0.5:
        warnings.append("일부 수집 Agent confidence 낮음")
    if dram and dram.meta.confidence < 0.5:
        warnings.append("D램/HBM 수집 confidence 낮음")
    if dram and dram.ddr5_spot_price_usd is not None and not 0.5 <= dram.ddr5_spot_price_usd <= 200:
        errors.append(f"DDR5 현물가 범위 이탈: {dram.ddr5_spot_price_usd}")
    if dram and dram.ddr5_spot_change_pct is not None and abs(dram.ddr5_spot_change_pct) > 50:
        errors.append(f"DDR5 변동률 범위 이탈: {dram.ddr5_spot_change_pct}")
    if flow and flow.meta.confidence < 0.5:
        warnings.append("KRX 수급 수집 confidence 낮음")
    if flow and flow.samsung_pbr is not None and not 0 <= flow.samsung_pbr <= 10:
        errors.append(f"삼성전자 PBR 범위 이탈: {flow.samsung_pbr}")
    if flow and flow.hynix_pbr is not None and not 0 <= flow.hynix_pbr <= 10:
        errors.append(f"SK하이닉스 PBR 범위 이탈: {flow.hynix_pbr}")
    if consensus and consensus.meta.confidence < 0.5:
        warnings.append("증권사 컨센서스 수집 confidence 낮음")
    if consensus and not consensus.stocks:
        warnings.append("증권사 컨센서스 결측")

    return ValidationPass(name="Pass 1 데이터 무결성", passed=not errors, warnings=warnings, errors=errors)


def pass2_consistency(main: MainScore, jensen: JensenScore) -> ValidationPass:
    warnings: list[str] = []
    errors: list[str] = []

    if main.score <= 35 and jensen.score >= 70:
        warnings.append("메인 약세이나 젠슨 유니버스 강세: 한국 고유 약세 가능성")
    if main.score >= 70 and jensen.score <= 35:
        warnings.append("메인 강세이나 젠슨 유니버스 약세: 랠리 지속성 의문")
    if abs(main.score - jensen.score) >= 35:
        warnings.append(f"메인/유니버스 괴리 큼: {main.score} vs {jensen.score}")
    if main.weakest_factor and main.factors.get(main.weakest_factor, 50) <= 20:
        warnings.append(f"단일 최약 팩터 경고: {main.weakest_factor}")

    return ValidationPass(name="Pass 2 논리 정합성", passed=not errors, warnings=warnings, errors=errors)


def summarize_validation(passes: list[ValidationPass]) -> ValidationSummary:
    passed_count = sum(item.passed for item in passes)
    warnings = [warning for item in passes for warning in item.warnings]
    if passed_count == len(passes) and len(warnings) <= 1:
        grade = "A"
    elif passed_count == len(passes):
        grade = "B"
    elif passed_count >= 1:
        grade = "C"
    else:
        grade = "D"
    return ValidationSummary(grade=grade, passes=passes, warnings=warnings)
