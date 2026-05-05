from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.auth.dependencies import require_user_session
from app.common.response.base_response import BaseResponse
from app.domains.investment.adapter.outbound.external.langgraph_investment_workflow import (
    LangGraphInvestmentWorkflow,
)
from app.domains.investment.application.request.investment_decision_request import (
    InvestmentDecisionRequest,
)
from app.domains.investment.application.response.investment_decision_response import (
    InvestmentDecisionResponse,
)
from app.domains.investment.application.usecase.run_investment_decision_usecase import (
    RunInvestmentDecisionUseCase,
)
from app.infrastructure.config.settings import get_settings
from app.infrastructure.database.database import get_db

router = APIRouter(prefix="/investment", tags=["Investment"])


@router.post(
    "/decision",
    response_model=BaseResponse[InvestmentDecisionResponse],
    status_code=200,
)
async def investment_decision(
    body: InvestmentDecisionRequest,
    user_id: str = Depends(require_user_session),
    db: AsyncSession = Depends(get_db),
):
    """
    인증된 사용자의 투자 판단 질의를 받아 멀티 에이전트 워크플로우를 실행한다.

    - 인증: Cookie의 user_token 검증
    - 입력: 사용자의 투자 판단 요청 질의 텍스트
    - 흐름: Orchestrator → Retrieval → Analysis → Synthesis
    """

    settings = get_settings()
    workflow = LangGraphInvestmentWorkflow(
        api_key=settings.openai_api_key,
        serp_api_key=settings.serp_api_key,
        youtube_api_key=settings.youtube_api_key,
        db_session=db,
    )
    usecase = RunInvestmentDecisionUseCase(workflow=workflow)
    result = await usecase.execute(user_id=user_id, request=body)

    return BaseResponse.ok(data=result, message="투자 판단 참고 응답이 생성되었습니다.")
