"""ADR-0001: chart_interval / lookback_range 공통 검증·정규화.

라우터에서 직접 사용. UseCase·외부 클라이언트도 동일 모듈에서 import해
중복 정의를 피한다.

- VALID_CHART_INTERVALS: 봉 단위 (`/timeline`, `/dashboard/...` 등)
- VALID_LOOKBACK_RANGES: 조회 기간 (`/macro-timeline` 등)
- normalize_chart_interval: 레거시 "1Y" → "1Q" 매핑
- validate_chart_interval: 정규화 후 검증, 실패 시 AppException(400)
- validate_lookback_range: upper 후 검증, 실패 시 AppException(400)
"""

from app.common.exception.app_exception import AppException

VALID_CHART_INTERVALS: frozenset[str] = frozenset({"1D", "1W", "1M", "1Q"})
VALID_LOOKBACK_RANGES: frozenset[str] = frozenset(
    {"1M", "3M", "6M", "1Y", "2Y", "5Y", "10Y"}
)

_LEGACY_INTERVAL_ALIAS: dict[str, str] = {"1Y": "1Q"}


def normalize_chart_interval(chart_interval: str) -> str:
    """레거시 별칭 정규화 — 외부 입력 경계에서 호출."""
    return _LEGACY_INTERVAL_ALIAS.get(chart_interval, chart_interval)


def validate_chart_interval(chart_interval: str) -> str:
    """정규화 + 유효성 검사. 실패 시 AppException(400)."""
    normalized = normalize_chart_interval(chart_interval)
    if normalized not in VALID_CHART_INTERVALS:
        raise AppException(
            status_code=400,
            message=(
                f"유효하지 않은 chart_interval입니다. "
                f"사용 가능: {', '.join(sorted(VALID_CHART_INTERVALS))} "
                f"(레거시 '1Y'는 '1Q'로 자동 정규화)"
            ),
        )
    return normalized


def validate_lookback_range(lookback_range: str) -> str:
    """upper 정규화 + 유효성 검사. 실패 시 AppException(400)."""
    upper = lookback_range.upper()
    if upper not in VALID_LOOKBACK_RANGES:
        raise AppException(
            status_code=400,
            message=(
                f"유효하지 않은 lookback_range입니다. "
                f"사용 가능: {', '.join(sorted(VALID_LOOKBACK_RANGES))}"
            ),
        )
    return upper
