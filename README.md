# AlphaResearch — Backend

> 한국·미국 주식을 동시에 다루는 개인 투자 정보 플랫폼의 백엔드. FastAPI + Hexagonal Architecture + DDD 로 작성된 멀티 에이전트 시스템.

> ⚠️ **Status**: 이 프로젝트는 **로컬 개발 환경 전용** 입니다. 운영 서버는 배포되어 있지 않으며, 본 README 의 실행 가이드는 모두 로컬 머신 기준입니다.

[Frontend Repo](https://github.com/K-MG-0328/AlphaResearch-frontend) · [내부 가이드 (CLAUDE.md)](./CLAUDE.md) · [ADR](./docs/adr/)

---

## 핵심 기능

| 영역 | 설명 |
|---|---|
| **종목 분석 에이전트** (`agent`) | LangGraph 기반 멀티-노드 워크플로우. 종목 메타·가격·뉴스·공시·재무를 모아 LLM 으로 분석 응답을 생성 |
| **히스토리 에이전트** (`history_agent`) | 종목/매크로 이상치 탐지 + LLM 추론으로 "왜 그날 움직였나" 타임라인 생성 (큐레이션된 역사 이벤트 기반) |
| **인과관계 에이전트** (`causality_agent`) | OHLCV + FRED 거시 + 뉴스(GDELT/Finnhub/Naver/Yahoo) + 공시(DART/SEC EDGAR) 수집 후 가설 생성·검증 |
| **투자 시그널** (`investment`) | 멀티 시그널 분석 + 투자 의사결정 응답 |
| **대시보드 / 종목 테마 / 매크로** | 자산 프로필, 테마별 종목 그룹, FRED·GPR 지수 등 보조 데이터 |
| **인증 / OAuth** | Kakao OAuth 기반 단일 `auth` 도메인. Cookie + Bearer 양쪽 지원 |

## 기술 스택

- **언어 / 런타임**: Python 3.13 (async-first)
- **프레임워크**: FastAPI 0.135 · Uvicorn 0.41 · pydantic-settings
- **데이터베이스**: PostgreSQL 17 + pgvector · SQLAlchemy 2 (async) · Alembic
- **캐시**: Redis 8
- **LLM / Agent**: OpenAI · LangChain 1 · LangGraph 1
- **외부 데이터**: yfinance · pykrx · FRED · Finnhub · GDELT · Naver Search · DART · SEC EDGAR · YouTube · GPR Index
- **NLP**: Kiwipiepy (Korean morphological analyzer)
- **스케줄러**: APScheduler

## 아키텍처

Hexagonal Architecture + Domain-Driven Design 4 레이어. **Domain → Application → Adapter → Infrastructure** 의존성 단방향.

```
app/
├ domains/<domain>/                  # 도메인별로 4 레이어 격리
│   ├ domain/                        # Entity / VO / Domain Service (순수 Python)
│   ├ application/                   # UseCase, Request/Response DTO, Port (ABC)
│   ├ adapter/
│   │   ├ inbound/api/               # FastAPI Router (단순 위임)
│   │   └ outbound/                  # Repository / External API Client
│   └ infrastructure/                # ORM Model, Mapper
├ infrastructure/                    # 전역: DB Session, Redis, Settings, External 공통 Client
├ adapter/inbound/api/v1_router.py   # 모든 도메인 라우터 등록
└ main.py                            # FastAPI app entrypoint
```

레이어별 규칙은 [`CLAUDE.md`](./CLAUDE.md) 참조 (Domain 에 ORM/FastAPI import 금지 등).

## 도메인 구성

```
account · auth · agent · history_agent · causality_agent · investment
dashboard · stock · stock_theme · macro · smart_money · schedule
news · disclosure · sentiment · post · study · sentiment · company_profile · market_video
```

각 도메인은 자체 `domain/`, `application/`, `adapter/`, `infrastructure/` 를 갖고 독립적으로 진화.

## 빠른 시작

### 1. 클론 & 의존성 설치

```bash
git clone https://github.com/K-MG-0328/AlphaResearch-backend.git
cd AlphaResearch-backend
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 환경 변수 설정

```bash
cp .env.example .env
# .env 를 열어 최소한 다음 항목 채우기
#   POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB
#   JWT_SECRET_KEY    (openssl rand -hex 32 추천)
#   OPENAI_API_KEY    (LLM 사용)
#   KAKAO_CLIENT_ID   (로그인 사용 시)
```

### 3. DB / Redis 띄우기 (Docker)

```bash
docker compose up -d postgres redis
```

> `.env` 의 `POSTGRES_*` 가 미설정이면 docker-compose 가 fail-fast 합니다 (의도된 동작 — public repo 에 비밀번호 기본값을 남기지 않기 위함).

### 4. 마이그레이션

```bash
alembic upgrade head
```

### 5. 서버 실행

```bash
# 개발 (reload)
uvicorn main:app --reload --host 0.0.0.0 --port 33333

# 또는
python main.py
```

API 문서: <http://localhost:33333/docs> (Swagger), <http://localhost:33333/redoc>

## 환경 변수

전체 목록과 설명은 [`.env.example`](./.env.example) 에 주석으로 정리되어 있습니다. 영역별 분류:

- **필수**: `POSTGRES_*`, `JWT_SECRET_KEY`, `OPENAI_API_KEY`
- **OAuth (Kakao 로그인 사용 시)**: `KAKAO_CLIENT_ID`, `KAKAO_REDIRECT_URI`
- **외부 데이터 (선택)**: `NAVER_CLIENT_ID/SECRET`, `OPEN_DART_API_KEY`, `FINNHUB_API_KEY`, `FRED_API_KEY`, `YOUTUBE_API_KEY`, `SERP_API_KEY`
- **Observability (선택)**: `LANGSMITH_*`, `LANGCHAIN_*`
- **튜닝 (모두 default 보유)**: `OPENAI_FINANCE_AGENT_MODEL`, `HISTORY_*`, `MACRO_*` 등

## 주요 API 라우터

모두 `/api/v1` prefix.

| Prefix | 도메인 | 인증 |
|---|---|---|
| `/auth/*`, `/auth/kakao/*` | 회원가입·로그인·세션·OAuth | public/me |
| `/account/*`, `/users/me/watchlist/*` | 계정 / 관심종목 | require_user |
| `/agent/*` | 종목 분석 에이전트 | require_user_or_temp |
| `/history-agent/*` | 히스토리 / 매크로 타임라인 | public |
| `/investment/*` | 투자 시그널 | require_user |
| `/dashboard/*`, `/stock/*`, `/stocks/*` | 대시보드 / 자산 프로필 | mixed |
| `/macro/*`, `/smart-money/*` | 거시 지표 / 수급 | mixed |
| `/news/*`, `/disclosure/*`, `/sentiment/*` | 뉴스·공시·심리 | mixed |
| `/agent-schema` | 에이전트 응답 스키마 | public |
| `/health` | 헬스체크 | public |

## 테스트

```bash
pytest                                # 전체
pytest tests/domains/agent/           # 특정 도메인
pytest -k "test_collect_news"         # 패턴 매치
```

550+ 테스트 (단위 + 통합). DB 가 필요한 테스트는 `tests/conftest.py` 의 fixture 가 자동 처리.

## Git 워크플로우

- `main` 직접 푸시 금지. 작업 브랜치 → PR → **merge commit** 으로 머지 (squash 금지 — 원본 SHA 보존)
- 한 PR = 한 관심사. 동작 변경(계약)과 리팩토링은 별도 PR
- 자세한 가이드: [`CLAUDE.md`](./CLAUDE.md)

## Documentation

- [`CLAUDE.md`](./CLAUDE.md) — 레이어별 규칙, 네이밍, DI 흐름
- [`docs/adr/`](./docs/adr/) — Architecture Decision Records
- [`docs/`](./docs/) — 도메인별 설계·전략 문서

## License

Personal project. 별도 라이선스 명시 없음 — 코드 사용 전 작성자에게 문의 바랍니다.
