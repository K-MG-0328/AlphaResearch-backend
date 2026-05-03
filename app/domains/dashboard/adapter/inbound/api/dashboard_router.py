import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.chart_interval import VALID_CHART_INTERVALS, validate_chart_interval
from app.common.response.base_response import BaseResponse
from app.domains.dashboard.adapter.outbound.external.fred_macro_client import FredMacroClient
from app.domains.dashboard.adapter.outbound.external.yahoo_finance_stock_client import (
    YahooFinanceStockClient,
)
from app.domains.dashboard.adapter.outbound.persistence.nasdaq_repository_impl import (
    NasdaqRepositoryImpl,
)
from app.domains.dashboard.application.response.economic_event_response import EconomicEventsResponse
from app.domains.dashboard.application.response.macro_data_response import MacroDataResponse
from app.domains.dashboard.application.response.nasdaq_bar_response import NasdaqBarsResponse
from app.domains.dashboard.application.response.stock_bar_response import StockBarsResponse
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

_CHART_INTERVAL_DESC = (
    f"봉 단위: {' | '.join(sorted(VALID_CHART_INTERVALS))} (레거시 '1Y'는 '1Q'로 자동 정규화)"
)


@router.get("/nasdaq", response_model=BaseResponse[NasdaqBarsResponse])
async def get_nasdaq_bars(
    chart_interval: str = Query("1M", alias="chartInterval", description=_CHART_INTERVAL_DESC),
    db: AsyncSession = Depends(get_db),
):
    """나스닥(^IXIC) OHLCV 일봉 데이터를 반환합니다."""
    chart_interval = validate_chart_interval(chart_interval)

    result = await GetNasdaqBarsUseCase(
        nasdaq_repository=NasdaqRepositoryImpl(db),
    ).execute(period=chart_interval)

    return BaseResponse.ok(data=result)


@router.get("/macro", response_model=BaseResponse[MacroDataResponse])
async def get_macro_data(
    chart_interval: str = Query("1M", alias="chartInterval", description=_CHART_INTERVAL_DESC),
):
    """거시경제 지표(기준금리·CPI·실업률)를 FRED API에서 실시간 조회합니다."""
    chart_interval = validate_chart_interval(chart_interval)

    result = await GetMacroDataUseCase(
        fred_macro_port=FredMacroClient(),
    ).execute(period=chart_interval)

    return BaseResponse.ok(data=result)


@router.get("/economic-events", response_model=BaseResponse[EconomicEventsResponse])
async def get_economic_events(
    chart_interval: str = Query("1M", alias="chartInterval", description=_CHART_INTERVAL_DESC),
):
    """경제 이벤트(기준금리·CPI·실업률 발표 이력)를 FRED API에서 실시간 조회합니다.

    chart_interval별 날짜 범위: 1D=365일 / 1W=1,095일 / 1M=1,825일 / 1Q=7,300일
    """
    chart_interval = validate_chart_interval(chart_interval)

    result = await GetEconomicEventsUseCase(
        fred_macro_port=FredMacroClient(),
    ).execute(period=chart_interval)

    return BaseResponse.ok(data=result)


@router.get("/stocks/{ticker}/bars", response_model=BaseResponse[StockBarsResponse])
async def get_stock_bars(
    ticker: str,
    chart_interval: str = Query("1D", alias="chartInterval", description=_CHART_INTERVAL_DESC),
    redis: aioredis.Redis = Depends(get_redis),
):
    """개별 종목 OHLCV 시계열 데이터를 반환합니다. (yfinance + Redis 캐시)"""
    chart_interval = validate_chart_interval(chart_interval)

    result = await GetStockBarsUseCase(
        stock_bars_port=YahooFinanceStockClient(),
        redis=redis,
    ).execute(ticker=ticker.upper(), period=chart_interval)

    return BaseResponse.ok(data=result)


# §13.4 C: /price-events 엔드포인트 철거.
# PRICE 카테고리(LOW_52W/HIGH_52W/SURGE/PLUNGE/GAP)는 `/history-agent/anomaly-bars`
# 엔드포인트가 차트 이상치 봉 마커로 대체.
#
# /nasdaq/collect (수동 트리거) 엔드포인트도 철거. 나스닥 수집은 APScheduler의
# `collect_nasdaq_bars` job(`app/infrastructure/scheduler/nasdaq_jobs.py`)이 담당.
