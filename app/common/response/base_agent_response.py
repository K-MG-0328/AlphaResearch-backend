"""Phase H4 — 4개 에이전트 도메인이 공유하는 응답 메타 필드.

응답 구조 일관성을 위해 도입. 기존 응답 클래스가 이 base 를 상속하면
status / error / metadata 필드가 추가된다 (additive — 기존 필드 0 변경).

Frontend 영향: 새 필드만 추가. 옛 필드는 그대로.
"""

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AgentResponseStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"


class BaseAgentResponse(BaseModel):
    """에이전트 응답 공용 메타 필드.

    각 에이전트(agent / history_agent / causality_agent / investment) 의
    Response DTO 가 상속해 사용한다.

    - status: 호출 결과 판정 (성공/부분 성공/오류).
    - error: 오류 메시지 (status == ERROR 또는 PARTIAL 일 때 사용).
    - metadata: 진단/디버그 보조 키 (예: latency_ms, model 등). 비어 있어도 무방.
    """

    status: AgentResponseStatus = AgentResponseStatus.SUCCESS
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
