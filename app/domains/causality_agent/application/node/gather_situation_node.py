import asyncio
import logging
from datetime import date as _date
from typing import Any, Dict, List

import yfinance as yf

from app.domains.causality_agent.di import get_economic_series_port
from app.domains.causality_agent.domain.state.causality_agent_state import CausalityAgentState
from app.infrastructure.config.settings import get_settings
from app.infrastructure.external.yahoo_ticker import normalize_yfinance_ticker

logger = logging.getLogger(__name__)


def _fetch_ohlcv_sync(ticker: str, start: str, end: str) -> list:
    t = yf.Ticker(normalize_yfinance_ticker(ticker))
    df = t.history(start=start, end=end, auto_adjust=True)
    bars = []
    for idx, row in df.iterrows():
        bars.append(
            {
                "date": idx.date().isoformat(),
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
                "volume": float(row["Volume"]),
            }
        )
    return bars


async def _fetch_ohlcv_cached(ticker: str, start: _date, end: _date) -> List[Dict[str, Any]]:
    """daily_bars DB를 우선 조회하고 비어 있으면 yfinance fallback + write-through.

    feature flag `causality_use_cached_bars` 가 True 일 때만 진입.
    """
    from app.domains.stock.market_data.adapter.outbound.external.cached_daily_bar_fetcher import (
        CachedDailyBarFetcher,
    )
    from app.domains.stock.market_data.adapter.outbound.external.yahoo_finance_daily_bar_fetcher import (
        YahooFinanceDailyBarFetcher,
    )
    from app.domains.stock.market_data.adapter.outbound.persistence.daily_bar_repository_impl import (
        DailyBarRepositoryImpl,
    )
    from app.infrastructure.database.database import AsyncSessionLocal

    yf_ticker = normalize_yfinance_ticker(ticker)
    async with AsyncSessionLocal() as db:
        fetcher = CachedDailyBarFetcher(
            repository=DailyBarRepositoryImpl(db),
            fallback=YahooFinanceDailyBarFetcher(),
        )
        bars = await fetcher.fetch(ticker=yf_ticker, start=start, end=end)

    return [
        {
            "date": b.bar_date.isoformat(),
            "open": round(b.open, 4),
            "high": round(b.high, 4),
            "low": round(b.low, 4),
            "close": round(b.close, 4),
            "volume": float(b.volume),
        }
        for b in bars
    ]


async def gather_situation(state: CausalityAgentState) -> Dict[str, Any]:
    """OHLCV + FRED 경제지표를 병렬로 수집한다."""
    ticker = state["ticker"]
    start_date = state["start_date"]
    end_date = state["end_date"]
    errors: list = list(state.get("errors", []))

    logger.info("[CausalityAgent] [1/3] OHLCV + FRED 경제지표 수집 시작")
    use_cached = get_settings().causality_use_cached_bars
    if use_cached:
        logger.info("[CausalityAgent] OHLCV cached daily_bars 경로 활성")
        ohlcv_task = _fetch_ohlcv_cached(ticker, start_date, end_date)
    else:
        loop = asyncio.get_event_loop()
        ohlcv_task = loop.run_in_executor(
            None, _fetch_ohlcv_sync, ticker, start_date.isoformat(), end_date.isoformat()
        )
    fred_task = get_economic_series_port().fetch_series(start_date, end_date)

    ohlcv_result, fred_result = await asyncio.gather(
        ohlcv_task, fred_task, return_exceptions=True
    )

    ohlcv_bars: list = []
    if isinstance(ohlcv_result, Exception):
        msg = f"OHLCV 수집 실패 ({ticker}): {ohlcv_result}"
        logger.warning("[CausalityAgent] %s", msg)
        errors.append(msg)
    else:
        ohlcv_bars = ohlcv_result

    fred_series: list = []
    if isinstance(fred_result, Exception):
        msg = f"FRED 수집 실패: {fred_result}"
        logger.warning("[CausalityAgent] %s", msg)
        errors.append(msg)
    else:
        fred_series = fred_result

    logger.info(
        "[CausalityAgent] [1/3] 완료: ohlcv=%d bars, fred=%d series",
        len(ohlcv_bars),
        len(fred_series),
    )
    return {"ohlcv_bars": ohlcv_bars, "fred_series": fred_series, "errors": errors}
