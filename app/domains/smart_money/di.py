"""Smart Money 도메인 의존성 주입 모듈.

라우터는 FastAPI ``Depends`` 로 여기의 팩토리를 호출한다. 외부 클라이언트는
stateless 이므로 모듈 스코프 singleton 으로 유지해 재생성 비용을 없앤다.
"""

from functools import lru_cache

import redis.asyncio as aioredis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception.app_exception import AppException
from app.domains.smart_money.adapter.outbound.external.dart_client import DartClient
from app.domains.smart_money.adapter.outbound.external.krx_investor_flow_client import (
    KrxInvestorFlowClient,
)
from app.domains.smart_money.adapter.outbound.external.sec_edgar_13f_client import SecEdgar13FClient
from app.domains.smart_money.adapter.outbound.persistence.global_portfolio_repository_impl import (
    GlobalPortfolioRepositoryImpl,
)
from app.domains.smart_money.adapter.outbound.persistence.investor_flow_repository_impl import (
    InvestorFlowRepositoryImpl,
)
from app.domains.smart_money.adapter.outbound.persistence.kr_portfolio_repository_impl import (
    KrPortfolioRepositoryImpl,
)
from app.domains.smart_money.application.usecase.collect_global_portfolio_usecase import (
    CollectGlobalPortfolioUseCase,
)
from app.domains.smart_money.application.usecase.collect_investor_flow_usecase import (
    CollectInvestorFlowUseCase,
)
from app.domains.smart_money.application.usecase.collect_kr_portfolio_usecase import (
    CollectKrPortfolioUseCase,
)
from app.domains.smart_money.application.usecase.get_concentrated_buying_usecase import (
    GetConcentratedBuyingUseCase,
)
from app.domains.smart_money.application.usecase.get_global_portfolio_usecase import (
    GetGlobalPortfolioUseCase,
)
from app.domains.smart_money.application.usecase.get_investor_flow_ranking_usecase import (
    GetInvestorFlowRankingUseCase,
)
from app.domains.smart_money.application.usecase.get_investor_flow_trend_usecase import (
    GetInvestorFlowTrendUseCase,
)
from app.domains.smart_money.application.usecase.get_kr_portfolio_usecase import (
    GetKrPortfolioUseCase,
)
from app.domains.smart_money.application.usecase.get_us_concentrated_buying_usecase import (
    GetUSConcentratedBuyingUseCase,
)
from app.infrastructure.cache.redis_client import get_redis
from app.infrastructure.config.settings import get_settings
from app.infrastructure.database.database import get_db


# ─────────────────── 외부 클라이언트 (stateless 싱글톤) ───────────────────


@lru_cache(maxsize=1)
def _krx_client() -> KrxInvestorFlowClient:
    settings = get_settings()
    return KrxInvestorFlowClient(krx_id=settings.krx_id, krx_pw=settings.krx_pw)


@lru_cache(maxsize=1)
def _sec_edgar_client() -> SecEdgar13FClient:
    settings = get_settings()
    return SecEdgar13FClient(user_agent=settings.sec_edgar_user_agent)


def _dart_client_or_raise() -> DartClient:
    """DART API key 가 비어있으면 라우터와 동일한 메시지로 400 raise.

    싱글톤이 아닌 매 호출마다 신규 생성. 이유: 키가 비어있는 상태로 lru_cache 에
    잡히면 이후 .env 갱신/재시작 없이 실행되는 시나리오에서 영구 실패한다. 호출
    빈도가 낮은 (manual collect) 엔드포인트라 비용 무시.
    """
    settings = get_settings()
    if not settings.open_dart_api_key:
        raise AppException(
            status_code=400,
            message=".env에 OPEN_DART_API_KEY가 설정되지 않았습니다. opendart.fss.or.kr에서 발급 후 설정해주세요.",
        )
    return DartClient(api_key=settings.open_dart_api_key)


# ─────────────────── Repository (per-request) ───────────────────


def get_investor_flow_repository(
    db: AsyncSession = Depends(get_db),
) -> InvestorFlowRepositoryImpl:
    return InvestorFlowRepositoryImpl(db)


def get_global_portfolio_repository(
    db: AsyncSession = Depends(get_db),
) -> GlobalPortfolioRepositoryImpl:
    return GlobalPortfolioRepositoryImpl(db)


def get_kr_portfolio_repository(
    db: AsyncSession = Depends(get_db),
) -> KrPortfolioRepositoryImpl:
    return KrPortfolioRepositoryImpl(db)


# ─────────────────── UseCase 팩토리 ───────────────────


def get_collect_investor_flow_usecase(
    repository: InvestorFlowRepositoryImpl = Depends(get_investor_flow_repository),
) -> CollectInvestorFlowUseCase:
    return CollectInvestorFlowUseCase(krx_port=_krx_client(), repository=repository)


def get_collect_global_portfolio_usecase(
    repository: GlobalPortfolioRepositoryImpl = Depends(get_global_portfolio_repository),
) -> CollectGlobalPortfolioUseCase:
    return CollectGlobalPortfolioUseCase(fetch_port=_sec_edgar_client(), repository=repository)


def get_investor_flow_ranking_usecase(
    repository: InvestorFlowRepositoryImpl = Depends(get_investor_flow_repository),
) -> GetInvestorFlowRankingUseCase:
    return GetInvestorFlowRankingUseCase(repository=repository)


def get_global_portfolio_usecase(
    repository: GlobalPortfolioRepositoryImpl = Depends(get_global_portfolio_repository),
) -> GetGlobalPortfolioUseCase:
    return GetGlobalPortfolioUseCase(repository=repository)


def get_concentrated_buying_usecase(
    repository: InvestorFlowRepositoryImpl = Depends(get_investor_flow_repository),
) -> GetConcentratedBuyingUseCase:
    return GetConcentratedBuyingUseCase(repository=repository)


def get_collect_kr_portfolio_usecase(
    repository: KrPortfolioRepositoryImpl = Depends(get_kr_portfolio_repository),
) -> CollectKrPortfolioUseCase:
    return CollectKrPortfolioUseCase(dart_client=_dart_client_or_raise(), repository=repository)


def get_kr_portfolio_usecase(
    repository: KrPortfolioRepositoryImpl = Depends(get_kr_portfolio_repository),
) -> GetKrPortfolioUseCase:
    return GetKrPortfolioUseCase(repository=repository)


def get_us_concentrated_buying_usecase(
    repository: GlobalPortfolioRepositoryImpl = Depends(get_global_portfolio_repository),
) -> GetUSConcentratedBuyingUseCase:
    return GetUSConcentratedBuyingUseCase(repository=repository)


def get_investor_flow_trend_usecase(
    repository: InvestorFlowRepositoryImpl = Depends(get_investor_flow_repository),
    redis: aioredis.Redis = Depends(get_redis),
) -> GetInvestorFlowTrendUseCase:
    return GetInvestorFlowTrendUseCase(repository=repository, redis=redis)
