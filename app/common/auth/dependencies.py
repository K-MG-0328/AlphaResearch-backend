"""Phase H5 — 4개 에이전트 도메인이 공유하는 인증 정책.

각 라우터에 흩어져 있던 _require_auth 커스텀 함수를 일원화. 정책 표:
- /api/v1/agent/*       — require_user_or_temp_session (user/temp 모두 허용)
- /api/v1/investment/*  — require_user_session (user_token 만 허용, user_id 반환)
- /api/v1/history-agent/* — 없음 (public, 인증 불필요)
- /api/v1/auth/*        — 라우터 내부 자체 처리 (로그인/세션/me 등)
"""

import logging
from typing import Optional

import redis.asyncio as aioredis
from fastapi import Depends, Request

from app.common.exception.app_exception import AppException
from app.infrastructure.cache.redis_client import get_redis

logger = logging.getLogger(__name__)

SESSION_KEY_PREFIX = "session:"
TEMP_TOKEN_KEY_PREFIX = "temp_token:"


def _extract_token(
    request: Request, cookie_name: str = "user_token"
) -> Optional[str]:
    """Cookie → Authorization Bearer 헤더 순으로 토큰 추출."""
    token = request.cookies.get(cookie_name)
    if token:
        return token
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.removeprefix("Bearer ").strip() or None
    return None


async def require_user_session(
    request: Request,
    redis: aioredis.Redis = Depends(get_redis),
) -> str:
    """본 세션(user_token)만 허용. token 문자열을 반환.

    investment 등 가입 후 사용자 전용 엔드포인트가 사용한다.
    """
    token = _extract_token(request, "user_token")
    if not token:
        raise AppException(status_code=401, message="인증이 필요합니다.")

    session_data = await redis.get(f"{SESSION_KEY_PREFIX}{token}")
    if not session_data:
        raise AppException(status_code=401, message="세션이 만료되었거나 유효하지 않습니다.")

    return token


async def require_user_or_temp_session(
    request: Request,
    redis: aioredis.Redis = Depends(get_redis),
) -> None:
    """user_token(본 세션) 과 temp_token(가입 전 임시 세션)을 모두 허용.

    /authentication/me 와 동일한 허용 범위를 유지해, 한쪽은 200 다른 쪽은 401 이
    튀는 UX 혼란을 제거한다. agent 등 가입 전후 모두 접근 가능한 엔드포인트가 사용.
    """
    user_token = request.cookies.get("user_token")
    temp_token = request.cookies.get("temp_token")
    auth_header = request.headers.get("authorization", "")

    if not user_token and auth_header.startswith("Bearer "):
        user_token = auth_header.removeprefix("Bearer ").strip() or None

    if not user_token and not temp_token:
        raise AppException(status_code=401, message="인증이 필요합니다.")

    if user_token:
        session_val = await redis.get(f"{SESSION_KEY_PREFIX}{user_token}")
        if session_val:
            return

    if temp_token:
        temp_val = await redis.get(f"{TEMP_TOKEN_KEY_PREFIX}{temp_token}")
        if temp_val:
            return

    raise AppException(status_code=401, message="세션이 만료되었거나 유효하지 않습니다.")
