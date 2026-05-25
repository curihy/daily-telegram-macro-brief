# Semiconductor Timing MVP

설계서 `integrated_system_design_v2_1.md`를 기반으로 만든 1차 MVP입니다.

목표:

- Agent 2: Nvidia/SOX/Jensen Universe 가격 데이터 수집
- Agent 3: 금리/환율/VIX 매크로 데이터 수집
- Agent 1: TrendForce 공개 DDR5 spot price + D램/HBM 뉴스 기반 추세 수집
- Flow Agent: KRX/네이버 금융 기반 삼성전자·SK하이닉스 외국인/기관 수급 보조 수집
- Main Score 0~100
- Jensen Universe Score 0~100
- Pass 1/2 검증
- SQLite 저장
- Telegram 텍스트 리포트 발송

## 실행

```bash
cd semiconductor-timing
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
DRY_RUN=1 python scripts/run_daily.py
```

실제 Telegram 발송:

```bash
DRY_RUN=0 python scripts/run_daily.py
```

## 현재 MVP에서 의도적으로 미룬 것

- Gmail HTML 이메일 발송
- 백테스트 기반 Pass 3
- 완전한 멀티에이전트 병렬 오케스트레이션

위 항목들은 데이터 소스 안정화 후 Phase 2부터 붙입니다.

## D램/HBM 수집 주의

TrendForce/DRAMeXchange 상세 장기 차트와 일부 계약가 데이터는 멤버십/로그인 영역입니다. 현재 MVP는 공개 `TrendForce price` 페이지의 DDR5 spot row를 best-effort로 파싱하고, TrendForce/DRAMeXchange 관련 공개 뉴스 헤드라인으로 HBM 공급 타이트와 계약가 추세를 보조 판단합니다.
