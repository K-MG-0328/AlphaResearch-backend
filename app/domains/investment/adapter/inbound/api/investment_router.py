import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception.app_exception import AppException
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
from app.infrastructure.cache.redis_client import get_redis
from app.infrastructure.config.settings import get_settings
from app.infrastructure.database.database import get_db

SESSION_KEY_PREFIX = "session:"

router = APIRouter(prefix="/investment", tags=["Investment"])


async def _require_auth(request: Request, redis: aioredis.Redis) -> str:
    """쿠키 → Authorization 헤더 순으로 토큰을 확인하고 user_id를 반환한다."""
    token = request.cookies.get("user_token")
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip() or None
    if not token:
        raise AppException(status_code=401, message="인증이 필요합니다.")

    session_data = await redis.get(f"{SESSION_KEY_PREFIX}{token}")
    if not session_data:
        raise AppException(status_code=401, message="세션이 만료되었거나 유효하지 않습니다.")

    return token


@router.post(
    "/decision",
    response_model=BaseResponse[InvestmentDecisionResponse],
    status_code=200,
)
async def investment_decision(
    request: Request,
    body: InvestmentDecisionRequest,
    redis: aioredis.Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """
    인증된 사용자의 투자 판단 질의를 받아 멀티 에이전트 워크플로우를 실행한다.

    - 인증: Cookie의 user_token 검증
    - 입력: 사용자의 투자 판단 요청 질의 텍스트
    - 흐름: Orchestrator → Retrieval → Analysis → Synthesis
    """
    user_id = await _require_auth(request, redis)

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
