"""Phase H6 — causality_agent LangGraph workflow UseCase 래퍼.

기존 함수 기반 호출(`causality_agent_workflow.run_causality_agent`)을
UseCase 클래스로 감싸 4 에이전트 도메인의 호출 패턴을 통일.

라우터는 추가하지 않는다 (causality_agent 는 history_agent 내부에서만 호출).
함수 진입점은 그대로 유지하여 테스트의 monkeypatch 호환을 보존 — UseCase 는
호출 시점에 모듈 속성을 lookup 한다.
"""

from datetime import date
from typing import Any, Dict, Optional

from app.domains.causality_agent.application import causality_agent_workflow
from app.domains.causality_agent.domain.state.causality_agent_state import (
    CausalityAgentState,
)


class RunCausalityAgentUseCase:
    """history_agent 가 가설 생성을 위해 호출하는 UseCase."""

    async def execute(
        self,
        *,
        ticker: str,
        start_date: date,
        end_date: date,
        detection_type: Optional[str] = None,
        anomaly_meta: Optional[Dict[str, Any]] = None,
    ) -> CausalityAgentState:
        # 호출 시점 lookup — 테스트의 monkeypatch(workflow_module, "run_causality_agent")
        # 가 그대로 동작하도록 모듈 속성을 통해 호출.
        return await causality_agent_workflow.run_causality_agent(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            detection_type=detection_type,
            anomaly_meta=anomaly_meta,
        )
