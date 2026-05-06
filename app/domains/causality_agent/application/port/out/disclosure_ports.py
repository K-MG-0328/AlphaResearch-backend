"""causality_agent — 공시 외부 소스 Port (Phase K1).

DART 한국 공시 — corp_code 기반 조회.
"""

from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Dict, List


class DartAnnouncementPort(ABC):
    """DART 한국 공시 조회 Port."""

    @abstractmethod
    async def fetch_announcements(
        self,
        ticker: str,
        corp_code: str,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]: ...
