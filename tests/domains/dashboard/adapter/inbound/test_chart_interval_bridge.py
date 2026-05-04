"""§13.8 Phase 3 → A5: chart_interval 검증 단위 테스트.

A5 에서 라우터의 `_validate_chart_interval` 가 `app/common/chart_interval.py` 의
`validate_chart_interval` 로 추출됨. 테스트도 신규 위치 import 로 갱신.

검증 동작 (A5 정의):
- 1D/1W/1M/1Q → 그대로 반환
- 1Y → 1Q 로 정규화 (legacy alias)
- 그 외 → AppException(400)
"""

import pytest

from app.common.chart_interval import validate_chart_interval
from app.common.exception.app_exception import AppException


class TestValidateChartInterval:
    @pytest.mark.parametrize("value", ["1D", "1W", "1M", "1Q"])
    def test_all_valid_values_pass_through(self, value):
        assert validate_chart_interval(value) == value

    def test_legacy_1Y_normalizes_to_1Q(self):
        # A5: yfinance 가 연봉을 미지원하므로 1Y → 1Q (분기봉) 자동 매핑
        assert validate_chart_interval("1Y") == "1Q"

    def test_invalid_value_raises_400(self):
        with pytest.raises(AppException) as exc:
            validate_chart_interval("5Y")
        assert exc.value.status_code == 400
        assert "유효하지 않은 chart_interval" in exc.value.message

    def test_empty_string_raises_400(self):
        with pytest.raises(AppException) as exc:
            validate_chart_interval("")
        assert exc.value.status_code == 400
