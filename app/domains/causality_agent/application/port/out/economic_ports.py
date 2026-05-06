"""causality_agent — 경제 시계열 외부 소스 Port (Phase K1).

FRED 거시 지표 + GPR 지수 (geo-political risk) 등 비-뉴스 경제 시계열 조회.
"""

from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Dict, List


class EconomicSeriesPort(ABC):
    """FRED 등 경제 지표 시계열 Port.

    날짜 범위로 사전 정의된 시리즈(FEDFUNDS / CPIAUCSL / UNRATE 등) 일괄 조회.
    """

    @abstractmethod
    async def fetch_series(
        self,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]: ...


class GprIndexPort(ABC):
    """Geo-political Risk 인덱스 등 단일 지수 시계열 Port."""

    @abstractmethod
    async def fetch(
        self,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]: ...
