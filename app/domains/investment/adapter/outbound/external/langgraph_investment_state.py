"""LangGraph Investment Workflow 의 공유 상태/상수/util.

워크플로우 본체와 분리하면 노드(혹은 향후 분리될 노드 파일들) 가 클래스 의존
없이 상태 타입과 util 함수를 import 할 수 있다. 동작 변경 0.
"""

from datetime import datetime, timezone
from typing import Any, Optional, TypedDict
from urllib.parse import parse_qs, urlparse

from app.domains.investment.domain.value_object.parsed_query import ParsedQuery


# ── 상수 ────────────────────────────────────────────────────────────────────

MAX_ITERATIONS = 10

# 영상당 최대 수집 댓글 수 / 댓글을 수집할 최대 영상 수
_MAX_COMMENTS_PER_VIDEO = 5
_MAX_VIDEOS_FOR_COMMENTS = 3

# 소스별 최대 실행 시간 (초) — 초과 시 해당 소스만 실패로 처리
RETRIEVAL_TIMEOUT_SECS = 30


# ── 공유 State 정의 ─────────────────────────────────────────────────────────

class InvestmentAgentState(TypedDict, total=False):
    user_id: str
    user_query: str

    # Query Parser 결과 (Orchestrator 첫 호출 시 기록)
    parsed_query: Optional[ParsedQuery]

    # Orchestrator 제어
    next_agent: str       # "retrieval" | "analysis" | "synthesis" | "end"
    iteration_count: int
    max_iterations: int

    # 각 에이전트 결과
    retrieved_data: list[dict[str, Any]]   # Retrieval Agent 결과
    investment_decision: dict[str, Any]    # Rule 기반 투자 판단 (buy/hold/sell)
    analysis_insights: dict[str, Any]      # Analysis Agent 결과
    final_response: str                    # Synthesis Agent 최종 응답


# ── 공용 util ───────────────────────────────────────────────────────────────

def parse_youtube_datetime(dt_str: str) -> datetime | None:
    """YouTube API published_at 문자열('2024-01-15T12:34:56Z')을 timezone-aware datetime으로 변환한다."""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now(tz=timezone.utc)


def extract_video_id(video_url: str) -> str | None:
    """YouTube URL에서 video_id를 추출한다. 파싱 실패 시 None 반환."""
    try:
        params = parse_qs(urlparse(video_url).query)
        ids = params.get("v", [])
        return ids[0] if ids else None
    except Exception:
        return None
