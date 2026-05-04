"""Schedule 도메인 의존성 주입 모듈.

라우터는 FastAPI ``Depends`` 로 여기의 팩토리를 호출한다. 외부 클라이언트와
composite provider 는 stateless 이므로 모듈 스코프 singleton 으로 유지해 매
요청마다 재생성하는 비용을 없앤다.
"""

from functools import lru_cache
from typing import Optional

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.news.adapter.outbound.external.naver_news_client import NaverNewsClient
from app.domains.news.adapter.outbound.external.serp_news_search_provider import (
    SerpNewsSearchProvider,
)
from app.domains.schedule.adapter.outbound.external.composite_economic_event_client import (
    CompositeEconomicEventClient,
)
from app.domains.schedule.adapter.outbound.external.composite_investment_info_provider import (
    CompositeInvestmentInfoProvider,
)
from app.domains.schedule.adapter.outbound.external.dart_corp_earnings_client import (
    DartCorpEarningsClient,
)
from app.domains.schedule.adapter.outbound.external.fred_economic_event_client import (
    FredEconomicEventClient,
)
from app.domains.schedule.adapter.outbound.external.fred_investment_info_client import (
    FredInvestmentInfoClient,
)
from app.domains.schedule.adapter.outbound.external.news_backed_event_disambiguator import (
    NewsBackedEventDisambiguator,
)
from app.domains.schedule.adapter.outbound.external.openai_event_impact_analyzer import (
    OpenAIEventImpactAnalyzer,
)
from app.domains.schedule.adapter.outbound.external.static_central_bank_event_client import (
    StaticCentralBankEventClient,
)
from app.domains.schedule.adapter.outbound.external.yahoo_investment_info_client import (
    YahooInvestmentInfoClient,
)
from app.domains.schedule.adapter.outbound.messaging.notification_broadcaster import (
    get_notification_broadcaster,
)
from app.domains.schedule.adapter.outbound.messaging.schedule_notification_publisher_impl import (
    ScheduleNotificationPublisher,
)
from app.domains.schedule.adapter.outbound.persistence.economic_event_repository_impl import (
    EconomicEventRepositoryImpl,
)
from app.domains.schedule.adapter.outbound.persistence.event_impact_analysis_repository_impl import (
    EventImpactAnalysisRepositoryImpl,
)
from app.domains.schedule.adapter.outbound.persistence.schedule_notification_repository_impl import (
    ScheduleNotificationRepositoryImpl,
)
from app.domains.schedule.application.usecase.get_economic_events_usecase import (
    GetEconomicEventsUseCase,
)
from app.domains.schedule.application.usecase.list_schedule_notifications_usecase import (
    ListScheduleNotificationsUseCase,
)
from app.domains.schedule.application.usecase.mark_schedule_notification_read_usecase import (
    MarkScheduleNotificationReadUseCase,
)
from app.domains.schedule.application.usecase.run_event_impact_analysis_usecase import (
    RunEventImpactAnalysisUseCase,
)
from app.domains.schedule.application.usecase.search_investment_info_usecase import (
    SearchInvestmentInfoUseCase,
)
from app.domains.schedule.application.usecase.sync_economic_events_usecase import (
    SyncEconomicEventsUseCase,
)
from app.domains.stock.domain.value_object.market_region import MarketRegion
from app.infrastructure.config.settings import get_settings
from app.infrastructure.database.database import get_db
from app.infrastructure.external.openai_responses_client import get_openai_responses_client


# ─────────────────── 외부 클라이언트 (stateless 싱글톤) ───────────────────


@lru_cache(maxsize=1)
def _fred_investment_client() -> FredInvestmentInfoClient:
    return FredInvestmentInfoClient(api_key=get_settings().fred_api_key)


@lru_cache(maxsize=1)
def _yahoo_investment_client() -> YahooInvestmentInfoClient:
    return YahooInvestmentInfoClient()


@lru_cache(maxsize=1)
def _fred_economic_event_client() -> FredEconomicEventClient:
    return FredEconomicEventClient(api_key=get_settings().fred_api_key)


@lru_cache(maxsize=1)
def _static_cbank_client() -> StaticCentralBankEventClient:
    return StaticCentralBankEventClient()


@lru_cache(maxsize=1)
def _dart_corp_client() -> DartCorpEarningsClient:
    """빈 키여도 client 생성. 실제 호출 시 fail (라우터 동작 보존)."""
    return DartCorpEarningsClient(api_key=get_settings().open_dart_api_key)


@lru_cache(maxsize=1)
def _indicator_provider() -> CompositeInvestmentInfoProvider:
    """FRED 1순위, Yahoo fallback. 두 엔드포인트(`investment-info` 류, `event-analysis` 류)에서 공유."""
    return CompositeInvestmentInfoProvider(
        providers=[_fred_investment_client(), _yahoo_investment_client()]
    )


@lru_cache(maxsize=1)
def _economic_event_fetch_port() -> CompositeEconomicEventClient:
    return CompositeEconomicEventClient(
        clients=[_fred_economic_event_client(), _static_cbank_client(), _dart_corp_client()],
    )


@lru_cache(maxsize=1)
def _analyzer() -> OpenAIEventImpactAnalyzer:
    return OpenAIEventImpactAnalyzer(client=get_openai_responses_client())


@lru_cache(maxsize=1)
def _disambiguator() -> Optional[NewsBackedEventDisambiguator]:
    """뉴스 검색 키가 모두 부재하면 None — UseCase 가 기존 동작으로 폴백."""
    settings = get_settings()
    serp = None
    if getattr(settings, "serp_api_key", ""):
        serp = SerpNewsSearchProvider(
            api_key=settings.serp_api_key,
            market_region=MarketRegion.US_NASDAQ,
        )
    naver = None
    if getattr(settings, "naver_client_id", "") and getattr(settings, "naver_client_secret", ""):
        naver = NaverNewsClient(
            client_id=settings.naver_client_id,
            client_secret=settings.naver_client_secret,
        )
    if serp is None and naver is None:
        return None
    return NewsBackedEventDisambiguator(
        serp_provider=serp,
        naver_client=naver,
        llm_client=get_openai_responses_client(),
    )


# ─────────────────── Repository (per-request) ───────────────────


def get_economic_event_repository(
    db: AsyncSession = Depends(get_db),
) -> EconomicEventRepositoryImpl:
    return EconomicEventRepositoryImpl(db=db)


def get_event_impact_analysis_repository(
    db: AsyncSession = Depends(get_db),
) -> EventImpactAnalysisRepositoryImpl:
    return EventImpactAnalysisRepositoryImpl(db=db)


def get_schedule_notification_repository(
    db: AsyncSession = Depends(get_db),
) -> ScheduleNotificationRepositoryImpl:
    return ScheduleNotificationRepositoryImpl(db=db)


def get_schedule_notification_publisher(
    repo: ScheduleNotificationRepositoryImpl = Depends(get_schedule_notification_repository),
) -> ScheduleNotificationPublisher:
    return ScheduleNotificationPublisher(repository=repo, broadcaster=get_notification_broadcaster())


# ─────────────────── UseCase 팩토리 ───────────────────


def get_search_investment_info_usecase() -> SearchInvestmentInfoUseCase:
    return SearchInvestmentInfoUseCase(provider=_indicator_provider())


def get_sync_economic_events_usecase(
    repository: EconomicEventRepositoryImpl = Depends(get_economic_event_repository),
) -> SyncEconomicEventsUseCase:
    return SyncEconomicEventsUseCase(
        fetch_port=_economic_event_fetch_port(),
        repository=repository,
        disambiguator=_disambiguator(),
    )


def get_economic_events_usecase(
    repository: EconomicEventRepositoryImpl = Depends(get_economic_event_repository),
) -> GetEconomicEventsUseCase:
    return GetEconomicEventsUseCase(repository=repository)


def get_run_event_impact_analysis_usecase(
    event_repo: EconomicEventRepositoryImpl = Depends(get_economic_event_repository),
    analysis_repo: EventImpactAnalysisRepositoryImpl = Depends(get_event_impact_analysis_repository),
    publisher: ScheduleNotificationPublisher = Depends(get_schedule_notification_publisher),
) -> RunEventImpactAnalysisUseCase:
    return RunEventImpactAnalysisUseCase(
        event_repository=event_repo,
        analysis_repository=analysis_repo,
        indicator_provider=_indicator_provider(),
        analyzer=_analyzer(),
        model_name=get_settings().openai_learning_model,
        notification_publisher=publisher,
    )


def get_list_schedule_notifications_usecase(
    repository: ScheduleNotificationRepositoryImpl = Depends(get_schedule_notification_repository),
) -> ListScheduleNotificationsUseCase:
    return ListScheduleNotificationsUseCase(repository=repository)


def get_mark_schedule_notification_read_usecase(
    repository: ScheduleNotificationRepositoryImpl = Depends(get_schedule_notification_repository),
) -> MarkScheduleNotificationReadUseCase:
    return MarkScheduleNotificationReadUseCase(repository=repository)
