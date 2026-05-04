"""Disclosure 도메인 의존성 주입 모듈.

`DisclosureAnalysisService` 는 stateless 싱글톤(생성자 없음, DB session 을 메서드
내부에서 직접 관리). 다른 도메인의 di.py 와 일관성을 위해 모듈 스코프 singleton 을
`@lru_cache` 로 노출하고 라우터는 `Depends(get_disclosure_analysis_service)` 로 받는다.
"""

from functools import lru_cache

from app.domains.disclosure.application.service.disclosure_analysis_service import (
    DisclosureAnalysisService,
)


@lru_cache(maxsize=1)
def get_disclosure_analysis_service() -> DisclosureAnalysisService:
    return DisclosureAnalysisService()
