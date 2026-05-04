"""timeline 이벤트 enrichment cache + AR 메트릭 service.

`HistoryAgentUseCase` 의 `_load/_apply/_save_enrichments` 와
`_apply_event_impact_metrics` 4 메서드를 응집 service 로 추출. UseCase 본체는 thin
wrapper 로 호출 → 외부 호출자(테스트 포함) 영향 0.

의존성 (모두 UseCase 가 주입한 동일 인스턴스를 service 가 위임 보유):
- `enrichment_repo`: 이벤트 title/causality 캐시
- `event_impact_repo` (선택): 5d/20d AR 메트릭 — None 이면 AR 주입 no-op
"""

import logging
from datetime import date
from typing import Dict, List, Optional, Tuple

from app.domains.history_agent.application.port.out.event_enrichment_repository_port import (
    EventEnrichmentRepositoryPort,
)
from app.domains.history_agent.application.response.timeline_response import (
    HypothesisResult,
    TimelineEvent,
)
from app.domains.history_agent.application.service.title_generation_service import (
    is_pseudo_announcement_title_str,
)
from app.domains.history_agent.domain.entity.event_enrichment import (
    EventEnrichment,
    compute_detail_hash,
)
from app.domains.stock.market_data.application.port.out.event_impact_metric_repository_port import (
    EventImpactMetricRepositoryPort,
)
from app.domains.stock.market_data.domain.entity.event_impact_metric import EventImpactMetric

logger = logging.getLogger(__name__)


class TimelineEnrichmentService:
    def __init__(
        self,
        enrichment_repo: EventEnrichmentRepositoryPort,
        event_impact_repo: Optional[EventImpactMetricRepositoryPort] = None,
    ) -> None:
        self._enrichment_repo = enrichment_repo
        self._event_impact_repo = event_impact_repo

    async def apply_event_impact_metrics(
        self, ticker: str, timeline: List[TimelineEvent]
    ) -> None:
        """event_impact_metrics 의 5d/20d AR을 timeline 이벤트에 in-place 주입.

        - repo 미주입(테스트 환경 등) 또는 timeline 빈 경우 no-op
        - status="OK" 메트릭만 abnormal_return_*d 채움. 다른 status 는 ar_status 만 기록
        - 같은 (ticker,date,type,detail_hash) 의 5d/20d 행 두 개를 한번에 매핑
        """
        if self._event_impact_repo is None or not timeline:
            return

        keys = [
            (
                ticker,
                e.date,
                e.type,
                compute_detail_hash(e.detail, e.constituent_ticker),
            )
            for e in timeline
        ]
        try:
            metrics = await self._event_impact_repo.find_by_event_keys(keys)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[HistoryAgent] event_impact 조회 실패 (graceful, AR 미주입): %s", exc,
            )
            return

        # (ticker, date, type, detail_hash) → {post_days: metric}
        by_key: Dict[Tuple[str, date, str, str], Dict[int, EventImpactMetric]] = {}
        for m in metrics:
            k = (m.ticker, m.event_date, m.event_type, m.detail_hash)
            by_key.setdefault(k, {})[m.post_days] = m

        applied = 0
        for event in timeline:
            k = (
                ticker,
                event.date,
                event.type,
                compute_detail_hash(event.detail, event.constituent_ticker),
            )
            windows = by_key.get(k)
            if not windows:
                continue
            applied += 1
            # 5d / 20d AR — status="OK" 인 행만 값 노출
            m5 = windows.get(5)
            m20 = windows.get(20)
            if m5 and m5.status == "OK":
                event.abnormal_return_5d = m5.abnormal_return_pct
            if m20 and m20.status == "OK":
                event.abnormal_return_20d = m20.abnormal_return_pct
            # 5d 우선으로 status/benchmark 결정 (없으면 20d)
            primary = m5 or m20
            if primary:
                event.ar_status = primary.status
                if primary.benchmark_ticker:
                    event.benchmark_ticker = primary.benchmark_ticker
        if applied:
            logger.info(
                "[HistoryAgent] AR 메트릭 적용: ticker=%s applied=%d/%d",
                ticker, applied, len(timeline),
            )

    async def load_enrichments(
        self, ticker: str, timeline: List[TimelineEvent]
    ) -> Dict[Tuple, EventEnrichment]:
        # title/causality는 v1 행에서만 로드(v2 행은 reclassified_type 캐시 용도).
        keys = [
            (
                ticker,
                e.date,
                e.type,
                compute_detail_hash(e.detail, e.constituent_ticker),
                "v1",
            )
            for e in timeline
        ]
        try:
            enrichments = await self._enrichment_repo.find_by_keys(keys)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[HistoryAgent] _load_enrichments 실패 — 빈 캐시로 진행: "
                "ticker=%s keys=%d error_type=%s error=%s",
                ticker, len(keys), type(exc).__name__, exc,
            )
            await self._enrichment_repo.rollback()
            return {}
        return {
            (e.ticker, e.event_date, e.event_type, e.detail_hash): e
            for e in enrichments
        }

    def apply_enrichments(
        self,
        ticker: str,
        timeline: List[TimelineEvent],
        db_map: Dict,
    ) -> List[TimelineEvent]:
        new_events = []
        for event in timeline:
            key = (
                ticker,
                event.date,
                event.type,
                compute_detail_hash(event.detail, event.constituent_ticker),
            )
            enrichment = db_map.get(key)
            # 옛 backend가 ANNOUNCEMENT에 _announcement_title()의 raw form을 그대로 캐시한 경우
            # cache hit이라도 LLM 재처리 + DB 갱신 대상으로 들어가도록 stale 판정.
            is_stale_pseudo = (
                enrichment is not None
                and event.category == "ANNOUNCEMENT"
                and is_pseudo_announcement_title_str(enrichment.title)
            )
            if enrichment and not is_stale_pseudo:
                event.title = enrichment.title
                if enrichment.causality:
                    event.causality = [HypothesisResult(**h) for h in enrichment.causality]
            else:
                new_events.append(event)
        return new_events

    async def save_enrichments(
        self, ticker: str, events: List[TimelineEvent]
    ) -> None:
        if not events:
            return
        enrichments = [
            EventEnrichment(
                ticker=ticker,
                event_date=e.date,
                event_type=e.type,
                detail_hash=compute_detail_hash(e.detail, e.constituent_ticker),
                title=e.title,
                causality=(
                    [h.model_dump() for h in e.causality] if e.causality else None
                ),
                importance_score=e.importance_score,
                items_str=e.items_str,
                classifier_version="v1",
            )
            for e in events
        ]
        try:
            saved = await self._enrichment_repo.upsert_bulk(enrichments)
            logger.info("[HistoryAgent] DB enrichment 저장: %d건", saved)
        except Exception as exc:  # noqa: BLE001
            # DB 스키마 미일치/트랜잭션 abort 시에도 응답 자체는 돌려주기 위해 graceful degradation.
            logger.error(
                "[HistoryAgent] DB enrichment 저장 실패 (응답은 정상 반환): "
                "ticker=%s events=%d error_type=%s error=%s",
                ticker, len(enrichments), type(exc).__name__, exc,
            )
            await self._enrichment_repo.rollback()
