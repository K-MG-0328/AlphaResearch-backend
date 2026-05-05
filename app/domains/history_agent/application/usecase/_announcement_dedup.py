"""History Agent UseCase 의 공시 중복 제거 helper.

DART/SEC EDGAR 가 같은 날 유사 공시를 발행할 때 병합 + ETF holding 이벤트와
ETF 자체 이벤트의 (date, category, title) 중복 제거. 모두 stateless 함수라
run_history_agent_usecase.py 의 본체 클래스 의존이 없다. 동작 변경 0.
"""

import logging
from typing import Dict, List, Optional

from app.domains.history_agent.application.response.timeline_response import TimelineEvent

logger = logging.getLogger(__name__)


# 이중상장(예: ADR) 기업에서 DART/SEC EDGAR가 같은 날 유사 공시를 발행할 때 병합.
# 소스 우선순위: 낮은 숫자일수록 우선. DART > SEC > YAHOO > 기타.
_ANNOUNCEMENT_SOURCE_PRIORITY = {"DART": 0, "SEC": 1, "SEC_EDGAR": 1, "YAHOO": 2}
_ANNOUNCEMENT_DEDUP_THRESHOLD = 0.8


def _jaccard_similarity(a: str, b: str) -> float:
    """공백 분할 기반 자카드 유사도. 짧은 공시 헤드라인에 충분하다."""
    set_a = set(a.split())
    set_b = set(b.split())
    if not set_a or not set_b:
        return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union else 0.0


def _announcement_source_rank(source: Optional[str]) -> int:
    if not source:
        return 99
    key = source.upper().replace(" ", "_")
    return _ANNOUNCEMENT_SOURCE_PRIORITY.get(key, 50)


def _dedupe_announcements(timeline: List[TimelineEvent]) -> List[TimelineEvent]:
    """같은 날 ANNOUNCEMENT detail 유사도가 높으면 source 우선순위로 1건만 남긴다.

    T2-7 Step 2 — Step 1(로깅만) 이후 데이터 검증 완료되어 실제 병합 활성화.
    알고리즘:
      1) date별 ANNOUNCEMENT 그룹
      2) 그룹 내에서 representative(현재까지 선정된 대표) 대비 유사도 ≥ threshold면 병합
         - source_rank가 더 낮은(우선순위 높은) 쪽을 대표로 승격
      3) 병합되지 않은 이벤트는 그대로 유지
    같은 날이라도 detail이 충분히 다른 공시는 그대로 병렬 노출된다.
    """
    buckets: Dict[str, List[TimelineEvent]] = {}
    others: List[TimelineEvent] = []
    for e in timeline:
        if e.category == "ANNOUNCEMENT":
            buckets.setdefault(e.date.isoformat(), []).append(e)
        else:
            others.append(e)

    kept_announcements: List[TimelineEvent] = []
    for date_key, events in buckets.items():
        if len(events) == 1:
            kept_announcements.extend(events)
            continue
        # 클러스터: 각 요소는 (representative, [members])
        clusters: List[TimelineEvent] = []
        for ev in events:
            matched = False
            for idx, rep in enumerate(clusters):
                if _jaccard_similarity(ev.detail, rep.detail) >= _ANNOUNCEMENT_DEDUP_THRESHOLD:
                    matched = True
                    # 더 우선순위 높은(rank 낮은) 이벤트를 대표로 승격
                    if _announcement_source_rank(ev.source) < _announcement_source_rank(rep.source):
                        logger.debug(
                            "[HistoryAgent] 공시 dedupe 승격: date=%s %s → %s",
                            date_key, rep.source, ev.source,
                        )
                        clusters[idx] = ev
                    break
            if not matched:
                clusters.append(ev)
        if len(clusters) < len(events):
            logger.info(
                "[HistoryAgent] 공시 dedupe: date=%s %d → %d",
                date_key, len(events), len(clusters),
            )
        kept_announcements.extend(clusters)

    return others + kept_announcements


def _dedupe_etf_timeline(events: List[TimelineEvent]) -> List[TimelineEvent]:
    """ETF 분해 시 holding 이벤트와 ETF 자체 이벤트가 (date, title) 기준 중복되면 1건만 남긴다.

    S2-7. SPY/QQQ 같은 ETF 는 상위 보유 종목별 CORPORATE/ANNOUNCEMENT 를 fan-out
    수집한 뒤 ETF 자체 이벤트와 합치는데, 같은 일자·동일 제목으로 두 번 노출되는
    경우가 있다. constituent_ticker 가 명시된 holding 이벤트를 우선 보존 — ETF 자체
    이벤트는 집계라 holding 단위가 더 구체적이다.
    """
    seen: Dict[tuple, TimelineEvent] = {}
    for e in events:
        key = (e.date, e.category, e.title)
        existing = seen.get(key)
        if existing is None:
            seen[key] = e
            continue
        # 둘 다 있을 때: constituent_ticker 명시된 쪽(holding) 우선
        if existing.constituent_ticker is None and e.constituent_ticker is not None:
            seen[key] = e
    return list(seen.values())
