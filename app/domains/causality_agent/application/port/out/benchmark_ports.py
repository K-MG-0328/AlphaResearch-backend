"""causality_agent — 벤치마크/관련 자산 외부 소스 Port (Phase K1).

related_assets / market_benchmark / sector_benchmark 등 비교 자산 시세 조회.
"""

from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Dict, List, Optional


class RelatedAssetsPort(ABC):
    """관련 자산 (sp500/usdkrw/wti 등) 일괄 조회 Port. ticker 무관."""

    @abstractmethod
    async def fetch(
        self,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]: ...


class MarketBenchmarkPort(ABC):
    """시장 벤치마크(국가별 대표 지수) 시세 Port. ticker 로 region 추정."""

    @abstractmethod
    async def fetch(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> Optional[Dict[str, Any]]: ...


class SectorBenchmarkPort(ABC):
    """섹터 ETF 벤치마크 시세 Port. ticker 로 섹터 mapping."""

    @abstractmethod
    async def fetch(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> Optional[Dict[str, Any]]: ...
