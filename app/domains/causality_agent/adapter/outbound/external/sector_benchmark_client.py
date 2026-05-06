"""
섹터 벤치마크 시계열 수집 (yfinance).

`MarketBenchmarkClient` 와 동일 패턴. ticker → 섹터 ETF 매핑이 있는 미국 종목만 수집.
한국 종목·인덱스·매핑 부재 ticker 는 None 반환.

`SectorBenchmark` state 필드는 `MarketBenchmark` 와 같은 dict 모양({symbol, name, bars}).
"""

import asyncio
import logging
from datetime import date
from typing import Any, Dict, Optional

import yfinance as yf

from app.domains.causality_agent.application.port.out.benchmark_ports import (
    SectorBenchmarkPort,
)
from app.infrastructure.external.sector_etf_directory import lookup_sector_etf

logger = logging.getLogger(__name__)


class SectorBenchmarkClient(SectorBenchmarkPort):
    """ticker → 섹터 ETF OHLCV(close) 시계열. 매핑 없으면 None."""

    async def fetch(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> Optional[Dict[str, Any]]:
        mapping = lookup_sector_etf(ticker)
        if mapping is None:
            return None
        symbol, name = mapping

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None, self._fetch_one, symbol, name, start_date, end_date
            )
        except Exception as exc:
            logger.warning(
                "[SectorBenchmark] %s 조회 실패 (ticker=%s): %s", symbol, ticker, exc
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
