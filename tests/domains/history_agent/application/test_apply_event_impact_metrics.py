"""PR3 — RunHistoryAgentUseCase._apply_event_impact_metrics 동작 검증."""
import asyncio
from datetime import date
from typing import List
from unittest.mock import MagicMock

from app.domains.history_agent.application.response.timeline_response import TimelineEvent
from app.domains.history_agent.application.usecase.run_history_agent_usecase import (
    RunHistoryAgentUseCase,
)
from app.domains.history_agent.domain.entity.event_enrichment import compute_detail_hash
from app.domains.stock.market_data.application.port.out.event_impact_metric_repository_port import (
    EventImpactMetricRepositoryPort,
)
from app.domains.stock.market_data.domain.entity.event_impact_metric import (
    EventImpactMetric,
)


class _StubImpactRepo(EventImpactMetricRepositoryPort):
    def __init__(self, metrics: List[EventImpactMetric]):
        self._metrics = metrics

    async def upsert_bulk(self, metrics):
        return 0

    async def find_by_event_keys(self, keys):
        return list(self._metrics)


def _make_usecase(impact_repo) -> RunHistoryAgentUseCase:
    # 필수 의존성은 MagicMock — _apply_event_impact_metrics 외 다른 메서드 호출 안 함.
    return RunHistoryAgentUseCase(
        stock_bars_port=MagicMock(),
        yfinance_corporate_port=MagicMock(),
        dart_corporate_client=MagicMock(),
        sec_edgar_port=MagicMock(),
        dart_announcement_client=MagicMock(),
        redis=MagicMock(),
        enrichment_repo=MagicMock(),
        asset_type_port=MagicMock(),
        event_impact_repo=impact_repo,
    )


def _event(detail: str = "sample", ev_date: date = date(2026, 3, 15)) -> TimelineEvent:
    return TimelineEvent(
        title="Crisis",
        date=ev_date,
        category="ANNOUNCEMENT",
        type="CRISIS",
        detail=detail,
    )


def _metric(
    ticker: str,
    ev_date: date,
    detail_hash: str,
    post_days: int,
    status: str = "OK",
    ar: float | None = 3.5,
) -> EventImpactMetric:
    return EventImpactMetric(
        ticker=ticker,
        event_date=ev_date,
        event_type="CRISIS",
        detail_hash=detail_hash,
        benchmark_ticker="^GSPC",
        pre_days=-1,
        post_days=post_days,
        status=status,
        cumulative_return_pct=ar,
        benchmark_return_pct=1.0 if ar else None,
        abnormal_return_pct=ar,
        sample_completeness=1.0,
    )


def test_no_op_when_repo_is_none():
    usecase = RunHistoryAgentUseCase(
        stock_bars_port=MagicMock(),
        yfinance_corporate_port=MagicMock(),
        dart_corporate_client=MagicMock(),
        sec_edgar_port=MagicMock(),
        dart_announcement_client=MagicMock(),
        redis=MagicMock(),
        enrichment_repo=MagicMock(),
        asset_type_port=MagicMock(),
        event_impact_repo=None,
    )
    e = _event()
    asyncio.run(usecase._apply_event_impact_metrics("AAPL", [e]))
    assert e.abnormal_return_5d is None
    assert e.ar_status is None


def test_no_op_when_timeline_empty():
    repo = _StubImpactRepo([])
    usecase = _make_usecase(repo)
    asyncio.run(usecase._apply_event_impact_metrics("AAPL", []))
    # 호출 자체가 안 일어나야 — repo.find_by_event_keys 가 호출되지 않은 것은 결과로 검증 못 하지만 예외 없이 종료


def test_applies_5d_and_20d_ar_for_ok_metrics():
    e = _event()
    detail_hash = compute_detail_hash(e.detail, e.constituent_ticker)
    repo = _StubImpactRepo([
        _metric("AAPL", e.date, detail_hash, post_days=5, ar=3.5),
        _metric("AAPL", e.date, detail_hash, post_days=20, ar=8.2),
    ])
    usecase = _make_usecase(repo)
    asyncio.run(usecase._apply_event_impact_metrics("AAPL", [e]))
    assert e.abnormal_return_5d == 3.5
    assert e.abnormal_return_20d == 8.2
    assert e.ar_status == "OK"
    assert e.benchmark_ticker == "^GSPC"


def test_non_ok_status_keeps_ar_value_none_but_records_status():
    e = _event()
    detail_hash = compute_detail_hash(e.detail, e.constituent_ticker)
    repo = _StubImpactRepo([
        _metric("AAPL", e.date, detail_hash, post_days=5, status="INSUFFICIENT_DATA", ar=None),
    ])
    usecase = _make_usecase(repo)
    asyncio.run(usecase._apply_event_impact_metrics("AAPL", [e]))
    assert e.abnormal_return_5d is None
    assert e.ar_status == "INSUFFICIENT_DATA"


def test_handles_repo_exception_gracefully():
    """repo 가 예외 던져도 timeline 은 그대로 반환 (AR 미주입)."""
    e = _event()

    class _ErrorRepo(EventImpactMetricRepositoryPort):
        async def upsert_bulk(self, metrics):
            return 0

        async def find_by_event_keys(self, keys):
            raise RuntimeError("DB 장애")

    usecase = _make_usecase(_ErrorRepo())
    asyncio.run(usecase._apply_event_impact_metrics("AAPL", [e]))
    assert e.abnormal_return_5d is None
    assert e.ar_status is None


def test_only_5d_metric_present_uses_it_for_status():
    """5d만 있고 20d 없을 때도 status/benchmark 가 들어가야 한다."""
    e = _event()
    detail_hash = compute_detail_hash(e.detail, e.constituent_ticker)
    repo = _StubImpactRepo([
        _metric("AAPL", e.date, detail_hash, post_days=5, ar=2.0),
    ])
    usecase = _make_usecase(repo)
    asyncio.run(usecase._apply_event_impact_metrics("AAPL", [e]))
    assert e.abnormal_return_5d == 2.0
    assert e.abnormal_return_20d is None
    assert e.ar_status == "OK"
