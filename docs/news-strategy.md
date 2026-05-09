# 뉴스 에이전트 운영 가이드

뉴스 에이전트는 네이버 뉴스 API로 주식 관련 뉴스를 수집하고, GPT를 통해 종목별 투자 신호(bullish / bearish / neutral)를 분석하는 서브 에이전트입니다.

---

## 목차

1. [서버 실행](#1-서버-실행)
2. [데이터 수집 흐름](#2-데이터-수집-흐름)
3. [분석 파이프라인](#3-분석-파이프라인)
4. [메인 에이전트 통합](#4-메인-에이전트-통합)
5. [스케줄러 자동화](#5-스케줄러-자동화)
6. [API 엔드포인트](#6-api-엔드포인트)
7. [DB 스키마](#7-db-스키마)
8. [환경 설정](#8-환경-설정)

---

## 1. 서버 실행

### 사전 요건

| 항목 | 버전 / 조건 |
|---|---|
| Python | 3.13 이상 |
| Docker Desktop | 실행 중 |
| PostgreSQL 컨테이너 | `pgvector_db` 포트 5433 |
| MySQL 컨테이너 | `legacy_mysql` 포트 3307 (현재는 PostgreSQL 단일화 — 이 항목은 stale) |

### Docker 컨테이너 시작

bash
docker compose up -d

### 서버 실행

bash
uvicorn main:app --reload --host 0.0.0.0 --port 33333

서버가 정상 시작되면 다음 로그가 출력됩니다.

INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:33333 (Press CTRL+C to quit)

> **Windows 주의사항**
> `main.py` 최상단에 `asyncio.WindowsSelectorEventLoopPolicy` 설정이 있습니다.
> Windows 환경에서 asyncpg가 ProactorEventLoop와 호환되지 않기 때문에 필수입니다.

---

## 2. 데이터 수집 흐름

뉴스 분석을 수행하려면 먼저 뉴스를 수집해야 합니다. 수집은 별도 엔드포인트를 수동 호출하거나 주기적으로 실행합니다.

### 수집 흐름 다이어그램

POST /api/v1/news/collect
        │
        ▼
CollectNaverNewsUseCase.execute()
        │
        ├─ 키워드 10개 × 페이지 최대 10개 순회
        │
        ▼
NaverNewsClient.search(keyword, display=100, start=N)
        │
        │  네이버 뉴스 API 호출
        │  (https://openapi.naver.com/v1/search/news.json)
        │
        ▼
CollectedNewsRepositoryImpl.exists_by_url()  ← URL 해시로 중복 체크
        │
        ├─ 중복이면 skip
        │
        └─ 신규이면 save → collected_news 테이블 (PostgreSQL)

### 수집 키워드 목록

`collect_naver_news_usecase.py`에 하드코딩되어 있습니다.

python
COLLECTION_KEYWORDS = [
    "코스피", "코스닥", "삼성전자", "SK하이닉스", "현대차",
    "금리", "환율", "반도체", "2차전지", "AI",
]

### 수집 용량

| 항목 | 값 |
|---|---|
| 요청당 기사 수 (`display`) | 100건 (API 최대) |
| 키워드당 최대 페이지 | 10페이지 |
| 키워드당 최대 수집 | 1,000건 |
| 전체 최대 수집 | **10,000건** (10 키워드 기준) |
| API 호출 수 / 1회 실행 | 최대 100회 |
| 네이버 API 일일 한도 | 25,000회 |

### 중복 제거 방식

python
# collected_news_repository_impl.py
url_hash = hashlib.sha256(url.encode()).hexdigest()
stmt = select(CollectedNewsOrm.id).where(CollectedNewsOrm.url_hash == url_hash)

기사 URL을 SHA-256으로 해싱하여 `url_hash` 컬럼에 저장합니다. 동일 URL이 재수집되면 DB 조회로 중복을 감지하고 skip합니다.

> **네이버 API 한계**
> 네이버 뉴스 API는 최근 뉴스만 제공합니다. `start=1000`까지 페이지를 넘겨도 수일~수주치 기사만 반환됩니다.
> 1년치 히스토리가 필요한 경우 BigKinds, 한국경제 API 등 별도 데이터 소스 도입이 필요합니다.

---

## 3. 분석 파이프라인

### 투자 신호 분석 흐름

GET /api/v1/news/agent-result?ticker=005930
        │
        ▼
AnalyzeNewsSignalUseCase.execute(ticker)
        │
        ├─ TICKER_TO_KEYWORDS 매핑으로 키워드 조회
        │    예) "005930" → ["삼성전자"]
        │
        ▼
CollectedNewsRepositoryImpl.find_by_keyword(keyword, limit=20)
        │  PostgreSQL에서 최신 20건 조회
        │
        ├─ 기사 없음 → SubAgentResponse.no_data("news", ...)
        │
        ▼
OpenAINewsSignalAdapter.analyze(ticker, company_name, articles)
        │
        │  gpt-5-mini 호출
        │  System Prompt: 한국 주식 감성 분석 전문가 역할
        │
        ▼
JSON 파싱 → InvestmentSignalResponse
        │
        ▼
SubAgentResponse.success_with_signal(signal, {"ticker": ticker}, elapsed_ms)

### 종목 코드 ↔ 키워드 매핑

`analyze_news_signal_usecase.py`에 정의되어 있습니다. 분석 가능한 종목은 아래와 같습니다.

| 종목코드 | 키워드 |
|---|---|
| 005930 | 삼성전자 |
| 000660 | SK하이닉스 |
| 005380 | 현대차 |
| 035420 | 네이버 |
| 035720 | 카카오 |
| 068270 | 셀트리온 |
| 207940 | 삼성바이오로직스 |
| 005490 | 포스코 |

> 새 종목 추가 시 `TICKER_TO_KEYWORDS`에 항목을 추가하고, `COLLECTION_KEYWORDS`에도 해당 키워드를 추가해야 합니다.

### GPT 분석 결과 스펙

GPT에게 아래 JSON 포맷으로만 응답하도록 System Prompt가 설정되어 있습니다.

json
{
  "signal": "bullish" | "bearish" | "neutral",
  "confidence": 0.0 ~ 1.0,
  "summary": "1~2문장 한국어 요약",
  "key_points": ["핵심 포인트1", "핵심 포인트2", ...]
}

| 필드 | 타입 | 설명 |
|---|---|---|
| `signal` | string | 투자 방향 (bullish / bearish / neutral) |
| `confidence` | float | 신호 확신도 (0.0 = 불확실, 1.0 = 매우 확실) |
| `summary` | string | 전체 평가 한국어 요약 (1~2문장) |
| `key_points` | list | 기사 기반 핵심 발견사항 2~5개 |

### 응답 상태 종류

| 상태 | 조건 | 설명 |
|---|---|---|
| `success` | 기사 존재 + GPT 분석 성공 | 투자 신호 포함 |
| `no_data` | 수집된 기사 없음 | 먼저 `/news/collect` 호출 필요 |
| `error` | GPT 호출 실패 | API 키 / 모델 권한 문제 확인 |

---

## 4. 메인 에이전트 통합

뉴스 에이전트는 `NewsSubAgentAdapter`를 통해 메인 에이전트(`ProcessAgentQueryUseCase`)에 통합되어 있습니다.

### 연동 구조

```
ProcessAgentQueryUseCase
    │
    └─ NewsSubAgentAdapter.analyze(ticker, query)
            │
            ├─ CollectedNewsRepositoryImpl(db).find_by_keyword(keyword, limit=20)
            │   (PostgreSQL collected_news 테이블에서 조회)
            │
            └─ AnalyzeNewsSignalUseCase.execute(ticker)
                    │
                    └─ OpenAINewsSignalAdapter.analyze(ticker, company_name, articles)
```

### 파일 위치

| 역할 | 파일 |
|------|------|
| 포트 인터페이스 | `app/domains/agent/application/port/news_agent_port.py` |
| 어댑터 구현 | `app/domains/agent/adapter/outbound/external/news_sub_agent_adapter.py` |
| 분석 UseCase | `app/domains/news/application/usecase/analyze_news_signal_usecase.py` |
| OpenAI 어댑터 | `app/domains/news/adapter/outbound/external/openai_news_signal_adapter.py` |

### 주의사항

- `NewsSubAgentAdapter`는 `db: AsyncSession`과 `api_key: str`을 생성자에서 주입받습니다.
- `agent_router.py`에서 `NewsSubAgentAdapter(db=db, api_key=settings.openai_api_key)`로 조립합니다.
- `TICKER_TO_KEYWORDS`에 없는 종목은 `SubAgentResponse.no_data("news", ...)`를 반환합니다.

---

## 5. 스케줄러 자동화

뉴스 수집은 두 가지 방식으로 자동화되어 있습니다.

### 서버 시작 시 초기 수집 (Bootstrap)

`main.py` lifespan에서 서버 시작 시 `job_collect_news()`를 자동 실행합니다.

```
서버 시작
    │
    └─ job_collect_news()  ← 최초 1회 즉시 실행
```

### 정기 수집 (APScheduler)

`disclosure_scheduler.py`에 등록된 daily job으로 매일 오전 6시(KST)에 자동 수집합니다.

| 항목 | 값 |
|------|-----|
| 실행 시각 | 매일 06:00 KST |
| job ID | `collect_news` |
| misfire_grace_time | 600초 |

서버 시작 로그에서 확인:
```
[Scheduler][CollectNews] Starting Naver news collection
[Scheduler][CollectNews] Complete — collected=XXX, skipped=XXX (X.Xs)
```

---

## 6. API 엔드포인트

### 4-1. 뉴스 수집

POST /api/v1/news/collect

네이버 뉴스 API에서 키워드별 뉴스를 수집하여 PostgreSQL에 저장합니다. 인증 불필요.

**Request:** Body 없음

**Response 예시**

json
{
  "status": "ok",
  "data": {
    "total_collected": 342,
    "skipped_duplicates": 658,
    "items": [
      {
        "title": "삼성전자, 3분기 영업이익 전망 상향",
        "description": "증권가에서 삼성전자의 3분기 실적 전망을 상향 조정했다.",
        "url": "https://...",
        "published_at": "Mon, 01 Apr 2026 09:00:00 +0900",
        "keyword": "삼성전자"
      }
    ]
  }
}

---

### 4-2. 뉴스 투자 신호 분석

GET /api/v1/news/agent-result?ticker={종목코드}

수집된 뉴스를 기반으로 GPT가 투자 신호를 분석합니다. 인증 불필요.

**Query Parameter**

| 파라미터 | 타입 | 필수 | 예시 |
|---|---|---|---|
| `ticker` | string | O | `005930` |

**Response 예시 (success)**

json
{
  "status": "ok",
  "data": {
    "agent": "news",
    "status": "success",
    "signal": "bullish",
    "confidence": 0.78,
    "summary": "삼성전자는 반도체 업황 회복과 AI 수요 증가로 긍정적인 모멘텀이 지속되고 있습니다.",
    "key_points": [
      "HBM 수요 급증으로 메모리 부문 실적 개선 기대",
      "파운드리 수주 증가 추세",
      "환율 하락이 수출 수익성에 부담 요인"
    ],
    "meta": { "ticker": "005930" },
    "elapsed_ms": 1823
  }
}

**Response 예시 (no_data)**

json
{
  "status": "ok",
  "data": {
    "agent": "news",
    "status": "no_data",
    "elapsed_ms": 12
  }
}

---

### 4-3. 뉴스 검색 (SerpAPI)

GET /api/v1/news/search?keyword={키워드}&page={페이지}&page_size={사이즈}

SerpAPI를 통해 실시간 뉴스를 검색합니다.

**Query Parameters**

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `keyword` | string | 필수 | 검색어 |
| `page` | int | 1 | 페이지 번호 |
| `page_size` | int | 10 | 페이지당 결과 수 (최대 100) |

---

### 4-4. 기사 저장

POST /api/v1/news/save

관심 기사를 저장합니다. 기사 링크에서 본문을 스크래핑하여 함께 저장합니다.

**Request Body**

json
{
  "title": "기사 제목",
  "link": "https://...",
  "source": "한국경제",
  "published_at": "2026-04-01",
  "snippet": "기사 요약"
}

---

### 4-5. 기사 감성 분석

GET /api/v1/news/analyze/{article_id}

저장된 기사의 본문을 GPT로 분석하여 핵심 키워드와 감성을 반환합니다.

---

## 7. DB 스키마

뉴스 에이전트는 두 개의 DB를 사용합니다.

| 테이블 | DB | 용도 |
|---|---|---|
| `collected_news` | PostgreSQL (포트 5433) | 네이버 API 수집 뉴스 |
| `saved_article` | MySQL (포트 3307) | 사용자가 저장한 기사 |

### collected_news (PostgreSQL)

sql
CREATE TABLE collected_news (
    id           SERIAL PRIMARY KEY,
    title        VARCHAR(500)  NOT NULL,
    description  TEXT,
    url          TEXT          NOT NULL,
    url_hash     VARCHAR(64)   NOT NULL UNIQUE,  -- SHA-256(url)
    published_at VARCHAR(100),
    keyword      VARCHAR(100)  NOT NULL,
    collected_at DATETIME      DEFAULT NOW()
);

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | int | PK, auto increment |
| `title` | varchar(500) | 기사 제목 (HTML 태그 제거됨) |
| `description` | text | 기사 요약 (HTML 태그 제거됨) |
| `url` | text | 원본 기사 URL |
| `url_hash` | varchar(64) | URL SHA-256 해시 (중복 방지용, UNIQUE) |
| `published_at` | varchar(100) | 발행일 (RFC 2822 형식) |
| `keyword` | varchar(100) | 수집 키워드 |
| `collected_at` | datetime | 수집 일시 |

> 서버 시작 시 `VectorBase.metadata.create_all`이 자동으로 테이블을 생성합니다.

---

### saved_article (MySQL)

sql
CREATE TABLE saved_article (
    id           INT           PRIMARY KEY AUTO_INCREMENT,
    title        VARCHAR(500)  NOT NULL,
    link         TEXT          NOT NULL,
    link_hash    VARCHAR(64)   NOT NULL UNIQUE,  -- SHA-256(link)
    source       VARCHAR(255),
    published_at VARCHAR(100),
    snippet      TEXT,
    content      TEXT,                           -- 스크래핑된 본문
    saved_at     DATETIME      DEFAULT NOW()
);

---

## 8. 환경 설정

### 필수 환경 변수 (`.env`)

dotenv
# PostgreSQL (뉴스 수집 데이터 저장)
postgres_user=postgres
postgres_password=postgres
postgres_host=127.0.0.1
postgres_port=5433          # ← Docker 컨테이너 포트 (Windows 네이티브 PostgreSQL과 충돌 방지)
postgres_db=vectordb

# MySQL (사용자 저장 기사)
MYSQL_USER=root
MYSQL_PASSWORD=your-mysql-password
MYSQL_HOST=localhost
MYSQL_PORT=3307
MYSQL_SCHEMA=multi_agent_db

# 네이버 뉴스 API
NAVER_CLIENT_ID=your_client_id
NAVER_CLIENT_SECRET=your_client_secret

# OpenAI (뉴스 감성 분석)
OPENAI_API_KEY=sk-proj-...

# SerpAPI (뉴스 검색)
SERP_API_KEY=your_serp_api_key

### 네이버 뉴스 API 키 발급

1. [네이버 개발자 센터](https://developers.naver.com) 접속
2. 애플리케이션 등록 → **검색** API 사용 설정
3. `Client ID`, `Client Secret` 발급 후 `.env`에 입력

### OpenAI API 키 주의사항

- 프로젝트 키(`sk-proj-...`) 사용 시 모델별 접근 권한을 확인해야 합니다.
- 현재 사용 모델: **`gpt-5-mini`**
- OpenAI 대시보드 → 해당 프로젝트 → Models에서 접근 가능 모델을 확인하세요.
- 모델 변경 시 `openai_news_signal_adapter.py`의 기본값을 수정합니다.

python
# openai_news_signal_adapter.py
def __init__(self, api_key: str, model: str = "gpt-5-mini"):  # 모델명 여기서 변경

### docker-compose.yml 포트 설정

yaml
postgres:
  image: pgvector/pgvector:pg17
  ports:
    - "5433:5432"   # 호스트 5433 → 컨테이너 5432
                    # Windows에 네이티브 PostgreSQL이 5432를 점유하므로 5433 사용

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `status: error`, `뉴스 감성 분석 중 오류` | OpenAI 모델 접근 권한 없음 또는 `temperature` 파라미터 미지원 | 모델명 확인, `temperature` 파라미터 제거 여부 확인 |
| `status: no_data` | 수집된 뉴스 없음 | `POST /api/v1/news/collect` 먼저 호출 |
| PostgreSQL 연결 실패 (WinError 64 / 10054) | Windows 포트 5432 충돌 (네이티브 PostgreSQL과 Docker 충돌) | `docker-compose.yml` 포트를 `5433:5432`로 변경 |
| 서버 시작 시 `vector_engine 연결 실패` 경고 | PostgreSQL 컨테이너 미실행 | `docker compose up -d postgres` 실행 |