"""causality_agent 의존성 주입 모듈 (Phase K2).

LangGraph 노드들이 사용하는 외부 클라이언트들을 모듈 스코프 싱글톤으로 유지.
기존엔 노드 함수가 매 호출마다 `FredEconomicClient()`, `GdeltClient()` 등을
직접 instantiate 했지만 클라이언트들은 모두 stateless 또는 connection pool
기반이므로 lru_cache 로 1회 생성 후 재사용해도 안전. 비용/메모리 ↓.

K3 후속 PR 에서 노드 함수가 이 팩토리를 호출하여 클라이언트를 받아오도록 변경.

history_agent/di.py 와 동일 패턴 (`@lru_cache(maxsize=1)`).
"""

from functools import lru_cache

from app.domains.causality_agent.adapter.outbound.external.dart_announcement_client import (
    DartAnnouncementClient,
)
from app.domains.causality_agent.adapter.outbound.external.finnhub_news_client import (
    FinnhubNewsClient,
)
from app.domains.causality_agent.adapter.outbound.external.fred_economic_client import (
    FredEconomicClient,
)
from app.domains.causality_agent.adapter.outbound.external.gdelt_client import GdeltClient
from app.domains.causality_agent.adapter.outbound.external.gpr_index_client import (
    GprIndexClient,
)
from app.domains.causality_agent.adapter.outbound.external.market_benchmark_client import (
    MarketBenchmarkClient,
)
from app.domains.causality_agent.adapter.outbound.external.naver_korean_news_client import (
    NaverKoreanNewsClient,
)
from app.domains.causality_agent.adapter.outbound.external.related_assets_client import (
    RelatedAssetsClient,
)
from app.domains.causality_agent.adapter.outbound.external.sector_benchmark_client import (
    SectorBenchmarkClient,
)
from app.domains.causality_agent.adapter.outbound.external.yahoo_finance_news_client import (
    YahooFinanceNewsClient,
)
from app.domains.causality_agent.application.port.out.benchmark_ports import (
    MarketBenchmarkPort,
    RelatedAssetsPort,
    SectorBenchmarkPort,
)
from app.domains.causality_agent.application.port.out.disclosure_ports import (
    DartAnnouncementPort,
)
from app.domains.causality_agent.application.port.out.economic_ports import (
    EconomicSeriesPort,
    GprIndexPort,
)
from app.domains.causality_agent.application.port.out.news_ports import (
    AnalystRatingPort,
    NewsArticlesPort,
)


# --- 시계열 / 경제 지표 ---

@lru_cache(maxsize=1)
def get_economic_series_port() -> EconomicSeriesPort:
    return FredEconomicClient()


@lru_cache(maxsize=1)
def get_gpr_index_port() -> GprIndexPort:
    return GprIndexClient()


# --- 뉴스 소스 ---

@lru_cache(maxsize=1)
def get_gdelt_news_port() -> NewsArticlesPort:
    return GdeltClient()


@lru_cache(maxsize=1)
def get_finnhub_news_port() -> NewsArticlesPort:
    return FinnhubNewsClient()


@lru_cache(maxsize=1)
def get_finnhub_analyst_rating_port() -> AnalystRatingPort:
    return FinnhubNewsClient()


@lru_cache(maxsize=1)
def get_naver_korean_news_port() -> NewsArticlesPort:
    return NaverKoreanNewsClient()


@lru_cache(maxsize=1)
def get_yahoo_finance_news_port() -> NewsArticlesPort:
    return YahooFinanceNewsClient()


# --- 공시 ---

@lru_cache(maxsize=1)
def get_dart_announcement_port() -> DartAnnouncementPort:
    return DartAnnouncementClient()


# --- 벤치마크 / 관련 자산 ---

@lru_cache(maxsize=1)
def get_related_assets_port() -> RelatedAssetsPort:
    return RelatedAssetsClient()


@lru_cache(maxsize=1)
def get_market_benchmark_port() -> MarketBenchmarkPort:
    return MarketBenchmarkClient()


@lru_cache(maxsize=1)
def get_sector_benchmark_port() -> SectorBenchmarkPort:
    return SectorBenchmarkClient()
