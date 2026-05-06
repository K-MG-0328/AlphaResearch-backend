"""
시장 벤치마크 시계열 수집 (yfinance).

종목의 region 에 따라 자동 분기:
- 한국 종목 → ^KS11 (KOSPI)
- 미국/그 외 → ^GSPC (S&P 500)

`RelatedAssetsClient` 와 분리한 이유: VIX/원유/금 등 매크로 자산과 시장 벤치마크는
용도가 다르다 — 매크로는 환경 컨텍스트, 벤치마크는 종목 alpha 계산용. state 키도 분리.
"""

import asyncio
import logging
from datetime import date
from typing import Any, Dict, Optional

import yfinance as yf

from app.domains.causality_agent.application.port.out.benchmark_ports import (
    MarketBenchmarkPort,
)
from app.domains.stock.domain.service.market_region_resolver import MarketRegionResolver

logger = logging.getLogger(__name__)


def _resolve_benchmark(ticker: str) -> tuple[str, str]:
    region = MarketRegionResolver.resolve(ticker)
    if region.is_korea():
        return "^KS11", "KOSPI"
    return "^GSPC", "S&P 500"


class MarketBenchmarkClient(MarketBenchmarkPort):
    """ticker → region → 시장 인덱스 OHLCV(close) 시계열."""

    async def fetch(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> Optional[Dict[str, Any]]:
        symbol, name = _resolve_benchmark(ticker)
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None, self._fetch_one, symbol, name, start_date, end_date
            )
        except Exception as exc:
            logger.warning(
                "[MarketBenchmark] %s 조회 실패 (ticker=%s): %s", symbol, ticker, exc
            )
            return None
        return result

    @staticmethod
    def _fetch_one(
        symbol: str,
        name: str,
        start_date: date,
        end_date: date,
    ) -> Optional[Dict[str, Any]]:
        t = yf.Ticker(symbol)
        df = t.history(
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            auto_adjust=True,
        )
        if df.empty:
            return None
        bars = []
        for idx, row in df.iterrows():
            bars.append(
                {
                    "date": idx.date().isoformat(),
                    "close": round(float(row["Close"]), 4),
                }
            )
        return {"symbol": symbol, "name": name, "bars": bars}
