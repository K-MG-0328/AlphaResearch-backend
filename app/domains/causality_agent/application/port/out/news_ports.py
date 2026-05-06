"""causality_agent — 뉴스/애널리스트 외부 소스 Port (Phase K1).

GDELT / Finnhub / Naver / Yahoo Finance 등이 공통적으로 구현하는
뉴스 기사 조회 인터페이스 + Finnhub 전용 애널리스트 지표 인터페이스.
"""

from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Dict, List


class NewsArticlesPort(ABC):
    """문자열 쿼리 + 기간 범위로 뉴스 기사를 조회하는 Port.

    구현체별 query 의 의미가 약간 다름 (keyword / ticker / symbol)
    이지만 호출 형태는 동일.
    """

    @abstractmethod
    async def fetch_articles(
        self,
        query: str,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]: ...


class AnalystRatingPort(ABC):
    """Finnhub 전용 — 애널리스트 buy/hold/sell + 실적 서프라이즈."""

    @abstractmethod
    async def get_recommendation_trend(self, symbol: str) -> List[Dict[str, Any]]: ...

    @abstractmethod
    async def get_earnings_surprise(self, symbol: str) -> List[Dict[str, Any]]: ...
