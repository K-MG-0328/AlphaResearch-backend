"""Dashboard 도메인 의존성 주입 모듈.

라우터는 FastAPI ``Depends`` 로 여기의 팩토리를 호출한다. 외부 클라이언트는
stateless 이므로 모듈 스코프 singleton 으로 유지해 재생성 비용을 없앤다.
"""

from functools import lru_cache

import redis.asyncio as aioredis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.dashboard.adapter.outbound.external.fred_macro_client import FredMacroClient
from app.domains.dashboard.adapter.outbound.external.yahoo_finance_stock_client import (
    YahooFinanceStockClient,
)
from app.domains.dashboard.adapter.outbound.persistence.nasdaq_repository_impl import (
    NasdaqRepositoryImpl,
)
from app.domains.dashboard.application.usecase.get_economic_events_usecase import (
    GetEconomicEventsUseCase,
)
from app.domains.dashboard.application.usecase.get_macro_data_usecase import GetMacroDataUseCase
from app.domains.dashboard.application.usecase.get_nasdaq_bars_usecase import (
    GetNasdaqBarsUseCase,
)
from app.domains.dashboard.application.usecase.get_stock_bars_usecase import GetStockBarsUseCase
from app.infrastructure.cache.redis_client import get_redis
from app.infrastructure.database.database import get_db


@lru_cache(maxsize=1)
def _fred_macro_port() -> FredMacroClient:
    return FredMacroClient()


@lru_cache(maxsize=1)
def _yfinance_stock_port() -> YahooFinanceStockClient:
    return YahooFinanceStockClient()


def get_nasdaq_bars_usecase(
    db: AsyncSession = Depends(get_db),
) -> GetNasdaqBarsUseCase:
    return GetNasdaqBarsUseCase(nasdaq_repository=NasdaqRepositoryImpl(db))


def get_macro_data_usecase() -> GetMacroDataUseCase:
    return GetMacroDataUseCase(fred_macro_port=_fred_macro_port())


def get_economic_events_usecase() -> GetEconomicEventsUseCase:
    return GetEconomicEventsUseCase(fred_macro_port=_fred_macro_port())


def get_stock_bars_usecase(
    redis: aioredis.Redis = Depends(get_redis),
) -> GetStockBarsUseCase:
    return GetStockBarsUseCase(stock_bars_port=_yfinance_stock_port(), redis=redis)
