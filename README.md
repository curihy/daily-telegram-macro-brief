# Daily Telegram Macro Brief

매일 아침 주식/매크로 지표를 모아 Telegram 채널로 보내는 최소 자동화 프로젝트입니다.

## 1. Telegram 봇 만들기

1. Telegram에서 `@BotFather` 검색
2. `/newbot` 실행
3. 봇 이름과 username 생성
4. 발급받은 bot token을 보관
5. 본인 Telegram 채널에 봇을 관리자로 추가
6. 공개 채널이면 `@channel_username`, 비공개 채널이면 chat id를 `TELEGRAM_CHAT_ID`로 사용

## 2. 로컬 환경 설정

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env`에 값을 넣습니다.

```bash
TELEGRAM_BOT_TOKEN=봇토큰
TELEGRAM_CHAT_ID=@채널username
FRED_API_KEY=FRED키
```

FRED 키는 선택이지만, 넣으면 미국 금리/크레딧 지표까지 포함됩니다.

## 3. 테스트 실행

텔레그램 발송 없이 리포트만 확인:

```bash
DRY_RUN=1 python macro_brief.py
```

실제 Telegram 채널로 발송:

```bash
python macro_brief.py
```

## 4. GitHub Actions로 매일 자동 실행

GitHub 저장소를 만든 뒤 아래 Secrets를 등록합니다.

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `FRED_API_KEY`

그리고 `.github/workflows/daily-macro.yml` 파일을 추가합니다.

```yaml
name: Daily Macro Brief

on:
  workflow_dispatch:
  schedule:
    - cron: "30 22 * * 1-5"

jobs:
  send:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python macro_brief.py
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          FRED_API_KEY: ${{ secrets.FRED_API_KEY }}
          REPORT_TITLE: Daily Macro Brief
          TIMEZONE: Asia/Seoul
```

`30 22 * * 1-5`는 UTC 기준 월-금 22:30이며, 한국시간으로 화-토 07:30입니다. 미국장 마감 후 한국 아침 브리핑에 맞춘 시간입니다.

## 5. 운영 팁

- 처음 1주일은 `workflow_dispatch`로 수동 실행하며 메시지 포맷을 다듬으세요.
- `yfinance`는 가벼운 MVP용으로 좋지만, 상업적/장기 운영은 Polygon, Alpha Vantage, Financial Modeling Prep 같은 계약형 API를 권장합니다.
- 리포트가 너무 길어지면 Telegram `sendMessage` 제한에 맞춰 섹션을 줄이거나 여러 메시지로 나누세요.
- 중요한 실패는 별도 개인 chat id로 보내도록 `ERROR_CHAT_ID`를 추가하면 운영이 편해집니다.
