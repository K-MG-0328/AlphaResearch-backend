# Disclosure Agent - 전략 및 운영 가이드

## 목차

1. [서버 최초 실행](#1-서버-최초-실행)
2. [부트스트랩 전략](#2-부트스트랩-전략)
3. [데이터 수집 흐름](#3-데이터-수집-흐름)
4. [문서 처리 파이프라인](#4-문서-처리-파이프라인)
5. [분석 파이프라인](#5-분석-파이프라인)
6. [LLM 프롬프트 전략](#6-llm-프롬프트-전략)
7. [캐싱 전략](#7-캐싱-전략)
8. [스케줄러 구성](#8-스케줄러-구성)
9. [외부 API 의존성](#9-외부-api-의존성)
10. [환경 설정](#10-환경-설정)
11. [DB 스키마 요약](#11-db-스키마-요약)
12. [트러블슈팅](#12-트러블슈팅)

---

## 1. 서버 최초 실행

### 사전 조건

- Docker + Docker Compose 설치
- `.env` 파일 설정 완료 (`backend/AlphaResearch-backend/.env`)

### 실행 순서

```bash
# 1. 프로젝트 루트에서 컨테이너 기동
cd /mnt/c/MultiAgent
docker compose up -d

# 2. 패키지 설치 + 서버 실행 (한 줄)
docker exec -it fastapi_app bash -c \
  "pip install -r /app/AlphaResearch-backend/requirements.txt -q && \
   pip install 'setuptools<82' -q && \
   cd /app/AlphaResearch-backend && \
   uvicorn main:app --reload --host 0.0.0.0 --port 8000"
```

### 포트 매핑

| 서비스 | 컨테이너 내부 | 외부 접근 |
|--------|-------------|-----------|
| FastAPI | 8000 | **localhost:33333** |
| PostgreSQL | 5432 | localhost:5432 |
| Redis | 6379 | localhost:6379 |

### 서버 기동 순서 (lifespan)

```
1. CREATE EXTENSION IF NOT EXISTS vector  (pgvector 활성화)
2. Base.metadata.create_all               (테이블 자동 생성)
3. SeedStockThemesUseCase.execute()       (주식 테마 초기 데이터)
4. job_bootstrap()                        (초기 데이터 적재)
5. scheduler.start()                      (정기 작업 스케줄러)
6. yield                                  (서버 Ready)
```

### 테스트 엔드포인트

```
GET http://localhost:33333/api/v1/disclosure/analyze?ticker=005930&analysis_type=full_analysis
```

- `ticker` (필수): 종목코드 (예: `005930`)
- `analysis_type` (선택): `flow_analysis` | `signal_analysis` | `full_analysis` (기본값)
- Swagger UI: `http://localhost:33333/docs`

---

## 2. 부트스트랩 전략

서버 최초 기동 시 DB가 비어있으면 자동으로 초기 데이터를 적재한다.

### 실행 조건

각 단계를 독립적으로 판단하여 필요한 단계만 실행한다.

| 조건 | 동작 |
|------|------|
| 기업 + 시총상위 + 공시 모두 존재 | 전체 스킵 |
| 기업 없음 | Step 2부터 실행 |
| 기업 있음 + 시총상위 없음 | Step 3부터 실행 |
| 기업 + 시총상위 있음 + 공시 없음 | Step 4만 실행 |

### 4단계 프로세스

```
[Step 1/4] 기존 데이터 확인
    └─ companies, is_top300, disclosures 존재 여부 체크

[Step 2/4] DART 전체 상장기업 목록 수집
    └─ DART corpCode.xml (ZIP) 다운로드 → XML 파싱
    └─ 상장기업 약 3,950건 → companies 테이블 upsert
    └─ 500건씩 배치 처리 (asyncpg 파라미터 제한 32,767개 대응)

[Step 3/4] 시총 상위 10개 기업 마킹
    ├─ 네이버 금융 API 시도 → 성공 시 사용
    └─ 실패 시 하드코딩 Top10 폴백 사용
    └─ update_top300_flags() → is_top300=true, is_collect_target=true

[Step 4/4] 상위 기업 공시 수집 (최근 90일)
    └─ DART API 5개 유형 (A/B/C/D/E) 병렬 조회
    └─ 상위 기업 corp_code로 필터링
    └─ disclosures 테이블 upsert (메타데이터: 제목, 날짜, 유형, 분류)
```

### 상수

| 상수 | 값 | 설명 |
|------|-----|------|
| `BOOTSTRAP_TOP_N` | 10 | 부트스트랩 시 시총 상위 기업 수 |
| `BOOTSTRAP_DISCLOSURE_DAYS` | 90 | 부트스트랩 시 공시 수집 기간 |

### 하드코딩 폴백 (Top 10)

네이버 금융 API 실패 시 사용되는 하드코딩 목록 (2026년 3월 기준):

| 순위 | 종목코드 | 기업명 |
|------|----------|--------|
| 1 | 005930 | 삼성전자 |
| 2 | 000660 | SK하이닉스 |
| 3 | 373220 | LG에너지솔루션 |
| 4 | 207940 | 삼성바이오로직스 |
| 5 | 005380 | 현대자동차 |
| 6 | 000270 | 기아 |
| 7 | 068270 | 셀트리온 |
| 8 | 005490 | POSCO홀딩스 |
| 9 | 035420 | NAVER |
| 10 | 055550 | 신한지주 |

### 에러 처리

부트스트랩 실패 시에도 서버는 정상 기동된다 (`try/except`로 감싸져 있음).

---

## 3. 데이터 수집 흐름

데이터 수집은 공시 **메타데이터**(제목, 날짜, 유형, 분류)를 `disclosures` 테이블에 저장하는 단계이다. 원문 처리는 별도 파이프라인(섹션 4)에서 수행한다.

### 3.1 기업 목록 수집 (RefreshCompanyListUseCase)

```
DART corpCode.xml (ZIP) → 전체 상장기업 파싱
    ↓
companies 테이블 upsert (약 3,950건)
    ↓
네이버 금융 API → 시총 상위 300개 조회 (KOSPI + KOSDAQ)
    ↓
update_top300_flags() → is_top300=true, market_cap_rank 설정
    ↓
우선주 자동 필터링 (stockEndType == "stock"만 포함)
```

**실행 주기**: 매일 02:00 (스케줄러)

### 3.2 전체 공시 수집 (CollectAllDisclosuresUseCase)

```
find_collect_targets(recent_days=30) → 수집 대상 기업 코드
    ├─ is_top300 == true
    └─ last_requested_at >= 30일 전 (분석 요청된 기업)
    ↓
DART API 5개 유형 병렬 조회 (asyncio.gather)
    ├─ A: 정기보고서 (사업/반기/분기)
    ├─ B: 주요사항보고서
    ├─ C: 임원·주요주주 특정증권
    ├─ D: 합병/분할/각종 공시
    └─ E: 지분 공시
    ↓
수집 대상 기업 필터링
    ↓
DisclosureClassifier.classify_group() → report/event/other 분류
DisclosureClassifier.is_core_disclosure() → 핵심 공시 여부
    ↓
disclosures 테이블 upsert (메타데이터만, 중복 자동 제거)
    ↓
CollectionJob 기록 (성공/실패/건수)
```

### 수집 대상 분류

| 분류 | 조건 | 예시 |
|------|------|------|
| **핵심 (is_core=true)** | 사업/반기/분기보고서, 유상증자, 합병, 분할, 대량보유 | 사업보고서, 주요사항보고서(유상증자결정) |
| **비핵심** | 그 외 모든 공시 | 임원 소유 보고, 기재정정, 의결권 위임 등 |

핵심/비핵심 모두 메타데이터는 동일하게 수집. 차이는 **문서 처리 대상 여부**(섹션 4)와 **LLM 프롬프트 상세도**(섹션 6).

### 3.3 증분 수집 (IncrementalCollectUseCase)

- **수집 대상**: B, C, D, E 유형 (시즌별 보고서 제외)
- **기간**: 마지막 수집 시점 ~ 현재
- **실행 주기**: 매시간 정시
- **DART 조회**: 병렬 (`asyncio.gather`)

### 3.4 시즌별 수집 (SeasonalCollectUseCase)

| 보고서 | 유형 | 수집 시기 |
|--------|------|-----------|
| 분기보고서 | A003 | 3월, 5월, 8월, 11월 15일 04:00 |
| 반기보고서 | A002 | 3월, 9월 15일 04:30 |
| 사업보고서 | A001 | 3월, 4월 1일 05:00 |

---

## 4. 문서 처리 파이프라인

**핵심 공시만** 대상으로 DART에서 원문을 다운받아 요약 + RAG 청크를 한 번에 생성한다.

### 설계 원칙

- **원문(raw_text)은 DB에 저장하지 않는다** — 메모리에서 즉시 가공 후 폐기
- DB에 저장하는 것: `summary_text`(500자), `parsed_json`, RAG 청크 + 임베딩
- 비핵심 공시는 원문 다운로드 자체를 하지 않음

### 처리 흐름 (ProcessDisclosureDocumentsUseCase)

```
find_unprocessed_core(limit=50) → 핵심 공시 중 미처리 건
    ↓
각 공시에 대해:
    ↓
DART document.xml (ZIP) 다운로드 → 메모리에 원문 보관
    ↓
DisclosureDocumentParser
    ├─ parse() → sections, tables, metadata (parsed_json)
    └─ generate_summary() → 원문 앞부분 500자 요약
    ↓
disclosure_documents 테이블 upsert (raw_text=None, summary_text + parsed_json만)
    ↓
TextChunker → 600자 청크, 100자 오버랩, SHA-256 해시
    ↓
OpenAI Embedding API (text-embedding-3-small, 1536차원)
    └─ 100건씩 배치 처리
    ↓
rag_document_chunks 테이블 upsert (embedding VECTOR(1536))
    ↓
원문 메모리에서 폐기
```

**실행 주기**: 매일 01:40 (스케줄러 `job_process_documents`)

### DB 저장 구조

| 테이블 | 저장하는 것 | 저장하지 않는 것 |
|--------|-----------|----------------|
| `disclosure_documents` | summary_text, parsed_json | ~~raw_text~~ |
| `rag_document_chunks` | chunk_text, embedding, section_title | - |

### 왜 원문을 저장하지 않는가?

원문은 **중간 재료**에 불과하다:
- 요약 생성의 입력 → 결과물(summary_text)만 필요
- RAG 청크 생성의 입력 → 결과물(chunk + embedding)만 필요
- 한번 가공되면 원문 자체는 다시 참조되지 않음
- 원문 저장 시 수만 자 × 수천 건 = 불필요한 스토리지 소비

---

## 5. 분석 파이프라인

### 전체 흐름

```
메인 에이전트
│
▼
DisclosureAnalysisService.analyze(ticker="005930", analysis_type="full_analysis")
│
├─ Phase 0: Redis 캐시 조회 (DB 접근 없음)
│   ├─ HIT  → AnalysisResponse 즉시 반환 (execution_time_ms=0)
│   └─ MISS → Phase 1로 진행
│
├─ Phase 1: DB 세션 (데이터 수집) ──────────────────────
│   │
│   │  ① ticker → corp_code 변환
│   │     CompanyRepositoryImpl.find_by_stock_code()
│   │
│   │  ② UseCase.gather_context() 호출
│   │     ├─ 공시 있음 (정상 플로우)
│   │     │   ├─ mark_as_collect_target() → last_requested_at 갱신
│   │     │   ├─ DisclosureClassifier → event/report 분류
│   │     │   ├─ 핵심 공시 요약 조회 (DB) + 미생성분 LLM 요약 생성 → DB 저장
│   │     │   ├─ OpenAI Embedding → 쿼리 벡터화
│   │     │   └─ pgvector search_similar() → RAG 컨텍스트 5건
│   │     │
│   │     └─ 공시 없음 (경량 플로우)
│   │         ├─ DART API 직접 조회 (최근 6개월)
│   │         └─ mark_as_collect_target() → 수집 대상 등록
│   │
│   └── DB 세션 해제 (커넥션 풀 반환)
│
├─ Phase 2: LLM 분석 (DB 세션 없음) ────────────────────
│   │
│   │  UseCase.analyze_from_context() 호출
│   │  ├─ AnalysisPromptBuilder → 분석 유형별 프롬프트 생성
│   │  ├─ OpenAI gpt-4.1-nano → LLM 분석 (max_tokens=4096, temp=0.3)
│   │  ├─ _parse_llm_response() → 키 매핑 + 정규화
│   │  └─ Redis 캐시 저장 (TTL 3600초)
│   │
│   └─ return AnalysisResponse
│
▼
메인 에이전트 ← AnalysisResponse 수신
```

### 온디맨드 LLM 요약 생성

분석 요청 시 핵심 공시에 대한 요약이 DB에 없으면 즉석에서 LLM으로 생성한다.

```
핵심 공시 8건 → DB 요약 조회 → 5건 존재
                             → 3건 미존재
                                 ↓
                    disclosure_documents에서 원문 확인
                    ├─ 원문 있음 → 앞 3000자 → LLM 요약 (gpt-4.1-nano) → DB 저장
                    └─ 원문 없음 → 스킵 (제목만 표시)
```

**재사용**: 한번 생성된 요약은 DB에 저장되므로 이후 요청에서는 LLM 호출 없이 재사용.

### 분석 유형별 차이

| | flow_analysis | signal_analysis | full_analysis |
|---|---|---|---|
| 목적 | 시계열 흐름 분석 | 투자 신호 분석 | 종합 분석 |
| 입력 공시 | 전체 50건 | **이벤트 우선** | 전체 50건 |
| signal/confidence | X | O | O |
| 시계열 추적 | O | X | O |
| RAG 근거 | O | O | O |

### LLM 응답 키 매핑

프롬프트별로 다른 출력 키를 파서가 통합 매핑한다:

| 프롬프트 출력 키 | 파서 매핑 |
|-----------------|-----------|
| `overall_signal` | → `signal` |
| `confidence` (str → float 변환) | → `confidence` |
| `investment_summary` / `timeline_summary` / `company_overview` | → `summary` |
| `key_events[]` | → `key_points[]` (`[날짜] 이벤트` 형식) |
| `signals[]` | → `key_points[]` (`[방향] 설명` 형식) |
| `risk_factors[]` + `positive_signals[]` | → `key_points[]` (폴백) |

### 세션 분리 전략

LLM 호출(2~5초) 동안 DB 커넥션을 점유하지 않도록 2단계로 분리:

| 단계 | 메서드 | DB 세션 | 수행 작업 |
|------|--------|---------|-----------|
| Phase 1 | `gather_context()` | 필요 | 공시 조회, 요약 조회/생성, RAG 검색 |
| Phase 2 | `analyze_from_context()` | **불필요** | 프롬프트 생성, LLM 호출, 캐시 저장 |

---

## 6. LLM 프롬프트 전략

### 핵심 원칙

- **핵심 공시**: 요약문 포함하여 상세 전달 (LLM이 깊이 분석)
- **비핵심 공시**: 카테고리별 건수만 전달 (LLM이 트렌드/분위기 파악)
- **RAG 근거**: 별도 섹션으로 원문 청크 제공 (깊은 근거 자료)

### 프롬프트 구조 예시 (full_analysis)

```
[System Message]
당신은 한국 주식 시장의 공시 분석 전문가입니다.
공시 데이터를 종합적으로 분석하여 시계열 흐름, 투자 신호, 리스크 요인을 통합 평가합니다.

[User Prompt]
## 공시 목록

### 핵심 공시 (5건 / 전체 50건)
- [2026-03-18] 주요사항보고서(자기주식취득결정) (분류: event)
  요약: 삼성전자 보통주 3,000,000주 취득 결정. 예정 금액 약 5,391억원.
        취득 기간 2026.03.19~2026.06.18. 주주가치 제고 목적.
- [2026-01-15] 사업보고서 (분류: report)
  요약: 2025년 연결 매출 302.2조원(전년비 +18%). 반도체 HBM 수요 증가.
- [2026-02-10] [기재정정]대량보유상황보고서 (분류: event)

### 기타 공시 현황
- 임원ㆍ주요주주 소유 보고: 18건
- 자금조달 관련: 3건
- 기타: 24건

## 참고 자료 (RAG 검색 결과)
[근거 1] 사업보고서 - Ⅱ. 사업의 내용
반도체 부문 매출은 전년 대비 23% 증가하였으며...

## 출력 형식 (JSON)
{ ... }
```

### 핵심 공시 분류 기준 (is_core)

| 핵심으로 분류 | 키워드 |
|-------------|--------|
| 정기보고서 | 사업보고서, 반기보고서, 분기보고서 |
| 자본 변동 | 유상증자 |
| 구조 변화 | 합병, 분할 |
| 지배구조 변화 | 대량보유 |

### 기타 공시 카테고리

| 카테고리 | 분류 기준 |
|----------|----------|
| 실적 관련 | 실적, 영업실적, 매출액, 영업이익 |
| 배당 관련 | 배당, 현금배당, 현물배당 |
| 자금조달 관련 | 유상증자, 전환사채, 신주인수권, 회사채 |
| 임원ㆍ주요주주 소유 보고 | 임원ㆍ주요주주, 대량보유, 지분 |
| 주요사항 | 합병, 분할, 주요사항보고, 영업양수/양도 |
| 기타 | 위에 해당하지 않는 모든 공시 |

### LLM 토큰 사용 시점

| 단계 | LLM 사용 | 설명 |
|------|---------|------|
| 데이터 수집 (스케줄러) | X | DART/네이버 API만 사용 |
| 문서 처리 (스케줄러) | **임베딩만** | RAG 청크 벡터화 |
| 분석 Phase 1 | **임베딩 1회** + **요약 0~N회** | RAG 쿼리 벡터화 + 미생성 요약 LLM 생성 |
| **분석 Phase 2** | **분석 1회** | gpt-4.1-nano 공시 분석 (유일한 대규모 LLM 호출) |
| 캐시 HIT | X | Redis에서 즉시 반환 |

---

## 7. 캐싱 전략

### Redis 캐시 구조

| 항목 | 값 |
|------|-----|
| 키 형식 | `disclosure:analysis:{ticker}:{analysis_type}` |
| TTL | 3600초 (1시간) |
| 저장 데이터 | `filings`, `signal`, `confidence`, `summary`, `key_points` |
| 직렬화 | JSON (ensure_ascii=False) |

### 캐시 조회 우선순위

```
1. Redis 캐시 체크 (ticker 기반, DB 접근 없음)
   ├─ HIT → 즉시 반환
   └─ MISS → DB 조회 + LLM 분석 → 결과 캐시 저장
```

### 캐시 키를 ticker 기반으로 한 이유

- corp_code 기반이면 캐시 조회 전에 DB에서 ticker→corp_code 변환 필요
- ticker 기반이면 **캐시 HIT 시 DB 접근이 0**

### 요약문 캐싱

분석 시 생성된 LLM 요약은 `disclosure_documents.summary_text`에 DB 저장된다.

- 같은 공시에 대한 이후 분석 요청 시 DB에서 바로 조회 (LLM 호출 0)
- 다른 기업이라도 같은 rcept_no를 참조하면 재사용

### Graceful Degradation

- Redis 연결 실패 시 `None` 반환 → 캐시 미적용으로 분석 진행
- 캐시 저장 실패 시 로그만 남기고 응답은 정상 반환
- 임베딩 모델 접근 실패 시 RAG 없이 분석 진행

---

## 8. 스케줄러 구성

APScheduler (AsyncIOScheduler, timezone: Asia/Seoul)

### 수시 수집

| 작업 | Cron | 설명 |
|------|------|------|
| `incremental_collect` | 매시간 :00 | 증분 공시 수집 (B/C/D/E 유형) |

### 일별 운영

| 작업 | Cron | 설명 |
|------|------|------|
| `refresh_company_list` | 매일 02:00 | DART 기업 목록 + 네이버 금융 시총 Top 300 |
| `process_documents` | 매일 01:40 | 핵심 공시 문서 처리 (요약 + RAG 청크 통합) |
| `cleanup_expired_data` | 매일 03:00 | 만료 데이터 정리 |

### 시즌별 보고서

| 작업 | Cron | 설명 |
|------|------|------|
| `seasonal_quarterly` | 3,5,8,11월 15일 04:00 | 분기보고서 (A003) |
| `seasonal_semiannual` | 3,9월 15일 04:30 | 반기보고서 (A002) |
| `seasonal_annual` | 3,4월 1일 05:00 | 사업보고서 (A001) |

### Misfire Grace Time

| 작업 유형 | Grace Time |
|-----------|-----------|
| 수시 | 300초 (5분) |
| 일별 | 600초 (10분) |
| 시즌별 | 3600초 (1시간) |

---

## 9. 외부 API 의존성

### DART Open API

| 엔드포인트 | 용도 | 호출 시점 |
|-----------|------|-----------|
| `opendart.fss.or.kr/api/corpCode.xml` | 전체 기업 코드 (ZIP/XML) | 부트스트랩, 스케줄러 (일 1회) |
| `opendart.fss.or.kr/api/list.json` | 공시 목록 조회 (페이지네이션) | 스케줄러 (매시간), 경량 분석 |
| `opendart.fss.or.kr/api/document.xml` | 공시 원문 (ZIP/HTML) | 스케줄러 (일 1회, 핵심만) |

- 인증: `crtfc_key` 파라미터
- 상태 코드: `000`=성공, `013`=데이터 없음

### 네이버 금융 API

| 엔드포인트 | 용도 |
|-----------|------|
| `m.stock.naver.com/api/stocks/marketValue/{market}` | 시가총액 상위 종목 |

- 마켓: KOSPI, KOSDAQ
- 페이지 사이즈: 최대 100
- 우선주 필터: `stockEndType == "stock"`
- KRX 직접 크롤링 대체 (Docker 환경에서 KRX 차단됨)

### OpenAI API

| 모델 | 용도 | 호출 시점 | 파라미터 |
|------|------|-----------|----------|
| `gpt-4.1-nano` | 공시 분석 | 분석 요청 시 (Phase 2) | max_tokens=4096, temp=0.3 |
| `gpt-4.1-nano` | 핵심 공시 요약 | 분석 요청 시 (Phase 1, 미생성분만) | 원문 3000자 → 요약 |
| `text-embedding-3-small` | RAG 임베딩 | 스케줄러 + 분석 시 | dimensions=1536 |

---

## 10. 환경 설정

### 필수 환경변수 (`.env`)

```env
# PostgreSQL
POSTGRES_USER=user
POSTGRES_PASSWORD=password
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=myapp

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# API Keys
OPENAI_API_KEY=sk-proj-...      # 필수: LLM 분석 + 임베딩
OPEN_DART_API_KEY=...            # 필수: 공시 데이터 수집
ANTHROPIC_API_KEY=...            # 다른 도메인에서 사용

# Auth
JWT_SECRET_KEY=...
NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
KAKAO_CLIENT_ID=...
KAKAO_REDIRECT_URI=...

# CORS
CORS_ALLOWED_FRONTEND_URL=http://localhost:3000

# LangSmith
LANGCHAIN_API_KEY=ls...
LANGCHAIN_PROJECT=disclosure-analysis 
LANGCHAIN_TRACING_V2=true
```

### Docker 리소스

| 서비스 | CPU | Memory |
|--------|-----|--------|
| PostgreSQL (pgvector:pg16) | 0.5 cores | 512MB |
| Redis (alpine) | 0.2 cores | 256MB |
| FastAPI Backend | - | 2GB |
| Next.js Frontend | - | 1GB |

---

## 11. DB 스키마 요약

### 테이블 관계

```
companies (corp_code PK)
    ├─→ disclosures (corp_code FK)
    │       └─→ disclosure_documents (rcept_no FK, CASCADE)
    │               └─→ rag_document_chunks (rcept_no FK, CASCADE)
    ├─→ company_data_coverage (corp_code FK)
    └─→ collection_jobs
            └─→ collection_job_items (job_id FK)
```

### 주요 테이블

| 테이블 | 레코드 수 (초기) | 용도 |
|--------|----------------|------|
| companies | ~3,950 | 전체 상장기업 |
| disclosures | ~2,300 (Top10 기준) | 공시 메타데이터 (핵심+비핵심 전부) |
| disclosure_documents | 0 (스케줄러/분석 시 채움) | 핵심 공시 요약 + 파싱 결과 (원문 미저장) |
| rag_document_chunks | 0 (스케줄러가 채움) | RAG 벡터 청크 (핵심 공시만) |
| collection_jobs | 자동 누적 | 수집 작업 이력 |

### companies 주요 컬럼

| 컬럼 | 용도 |
|------|------|
| `is_top300` | 시총 상위 300 여부 |
| `is_collect_target` | 공시 수집 대상 여부 |
| `last_requested_at` | 마지막 분석 요청 시각 |
| `market_cap_rank` | 시가총액 순위 |

### disclosures 주요 컬럼

| 컬럼 | 용도 |
|------|------|
| `is_core` | 핵심 공시 여부 (문서 처리 대상) |
| `disclosure_group` | report / event / other |
| `source_mode` | scheduled / ondemand |

---

## 12. 트러블슈팅

### DB 초기화

```bash
cd /mnt/c/MultiAgent
docker compose down
docker volume rm multiagent_postgres_data
docker compose up -d
```

### Redis 캐시 초기화

```bash
docker exec -it redis_cache redis-cli FLUSHALL
```

### 부트스트랩이 스킵될 때

기업 데이터가 이미 존재하면 부트스트랩이 스킵된다. DB를 리셋하거나, 수동으로 스케줄러 작업을 실행:

```bash
# 시총 Top 300 갱신
docker exec -it fastapi_app python -c "
import asyncio, sys
sys.path.insert(0, '/app/AlphaResearch-backend')
async def run():
    from app.infrastructure.database.database import AsyncSessionLocal
    from app.domains.disclosure.adapter.outbound.external.dart_corp_code_client import DartCorpCodeClient
    from app.domains.disclosure.adapter.outbound.external.krx_market_cap_client import KrxMarketCapClient
    from app.domains.disclosure.adapter.outbound.persistence.company_repository_impl import CompanyRepositoryImpl
    from app.domains.disclosure.application.usecase.refresh_company_list_usecase import RefreshCompanyListUseCase
    async with AsyncSessionLocal() as db:
        result = await RefreshCompanyListUseCase(
            company_repository=CompanyRepositoryImpl(db),
            dart_corp_code_port=DartCorpCodeClient(),
            krx_market_cap_port=KrxMarketCapClient(),
        ).execute()
        print(result.message)
asyncio.run(run())
"
```

### KRX/시가총액 조회 이슈

pykrx는 제거됨. 시가총액 조회는 네이버 금융 API로 대체.
- KRX 웹사이트는 Docker 컨테이너에서 크롤링 차단
- 네이버 금융 API는 KOSPI + KOSDAQ 통합 지원, 우선주 자동 필터링
- 네이버 API도 실패 시 부트스트랩은 하드코딩 Top10으로 폴백

### OpenAI 모델 접근 오류

`403 model_not_found` 에러 시 `.env`의 `OPENAI_API_KEY`에 연결된 프로젝트의 모델 접근 권한 확인.
현재 설정: `gpt-4.1-nano` (분석+요약), `text-embedding-3-small` (임베딩)

### pip 패키지가 컨테이너 재시작 시 사라지는 문제

컨테이너 이미지에 패키지가 포함되지 않아서 재시작 시 매번 설치 필요.
Dockerfile에 `RUN pip install -r requirements.txt`를 추가하거나 실행 스크립트에 포함.

---

## 13. 개선 이력

### RAG 검색 쿼리 개선

**파일**: `app/domains/disclosure/application/usecase/analysis_agent_graph.py`

**문제**: `_build_analysis_query()`가 `corp_code`를 단순 연결하는 방식이어서 임베딩 검색에 의미 있는 쿼리가 생성되지 않았음.

**변경 전**:
```python
parts = [f"corp_code {corp_code} disclosure analysis"]
if event_disclosures:
    parts.append(" ".join(d.report_nm for d in event_disclosures[:5]))
```

**변경 후**:
```python
base = f"{ticker} 사업현황 위험요소 성장전략 경영실적 주요사업"
if event_disclosures:
    events_text = " ".join(d.report_nm for d in event_disclosures[:3])
    return f"{base} {events_text}"
return base
```

**효과**: RAG 청크 검색 정확도 향상 → 공시 에이전트 처리 시간 20초 → 7~8초로 단축, confidence 개선.

---

### LLM 프롬프트 confidence 기준 완화

**파일**: `app/domains/disclosure/domain/service/analysis_prompt_builder.py`

**문제**: 프롬프트에 "RAG 자료가 부족하면 confidence 0.5 이하" 지침이 있었으나, 공시 RAG는 재무 수치가 아닌 사업 현황·위험 요소 등 정성적 내용을 담고 있어 불필요하게 낮은 confidence가 생성되었음.

**변경 내용**: 해당 지침 제거 후 아래 내용으로 대체:
```
RAG 자료에 재무 수치가 없더라도 사업 내용, 위험 요소, 전략 정보가 있으면 confidence 0.6 이상 가능
```

**효과**: confidence 0.4 → 0.75로 개선, key_points 2개 → 3개로 정상화.
