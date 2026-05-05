"""History Agent UseCase 의 lookback 윈도우 + region 매핑 helper.

봉 단위(`chart_interval`) 와 조회 기간(`period`) 매핑 + 지수/ETF 의 FRED 매크로
리전 매핑. 모두 stateless 데이터/순수 함수라 run_history_agent_usecase.py 의 본체
클래스 의존이 없다. 동작 변경 0.
"""

from datetime import date, timedelta
from typing import Dict


# ── 지수 → FRED 매크로 리전 매핑 ────────────────────────────────
_INDEX_REGION: Dict[str, str] = {
    "^IXIC": "US",
    "^GSPC": "US",
    "^DJI":  "US",
    "^KS11": "KR",
}
_DEFAULT_INDEX_REGION = "US"


# ── chart_interval → 이벤트 수집 lookback (§13.4 B) ─────────────
# 봉 단위 차트의 전체 범위에 맞춰 NEWS/MACRO 수집 윈도우를 정렬:
#   1D 일봉(1년 차트) → 1년 / 1W 주봉(3년) → 3년 / 1M 월봉(5년) → 5년
#   1Q 분기봉(20년) → 20년 / 1Y(legacy alias for 1Q) → 20년
_CHART_INTERVAL_LOOKBACK_DAYS: Dict[str, int] = {
    "1D": 365,
    "1W": 1_095,
    "1M": 1_825,
    "1Q": 7_300,
    "1Y": 7_300,
}
_DEFAULT_CHART_INTERVAL_LOOKBACK_DAYS = 365


# ── ETF → FRED 매크로 리전 매핑 ─────────────────────────────────
# 모르는 ETF는 _DEFAULT_INDEX_REGION(US)으로 처리.
_ETF_REGION: Dict[str, str] = {
    "SPY": "US", "QQQ": "US", "IWM": "US", "DIA": "US",
    "VOO": "US", "VTI": "US", "VEA": "US", "VWO": "US",
    "EWY": "KR", "EWJ": "US",  # EWJ는 일본 ETF, MACRO는 US fallback
    "069500": "KR", "229200": "KR",  # KODEX 200, KODEX 코스닥150
}


# ── period → 일수 변환 (lookbackRange API 와 별개의 내부 단축 매핑) ────
_PERIOD_DAYS: Dict[str, int] = {
    "1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365, "2Y": 730, "5Y": 1825,
}


def datetime_date_from_period(period: str) -> date:
    """period 문자열을 오늘 기준 시작일로 변환. 모르는 값은 90일 fallback."""
    days = _PERIOD_DAYS.get(period.upper(), 90)
    return date.today() - timedelta(days=days)
