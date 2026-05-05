import json
from typing import Optional

import redis.asyncio as aioredis

from app.domains.auth.application.port.out.temp_token_store_port import TempTokenStorePort
from app.domains.auth.domain.entity.temp_token import TempToken

TEMP_TOKEN_KEY_PREFIX = "temp_token:"


class TempTokenStore(TempTokenStorePort):
    def __init__(self, redis: aioredis.Redis):
        self._redis = redis

    async def save(self, temp_token: TempToken) -> None:
        data = json.dumps({
            "kakao_access_token": temp_token.kakao_access_token,
            "nickname": temp_token.nickname,
            "email": temp_token.email,
        })
        await self._redis.setex(
            f"{TEMP_TOKEN_KEY_PREFIX}{temp_token.token}",
            temp_token.ttl_seconds,
            data,
        )

    async def find_by_token(self, token: str) -> Optional[TempToken]:
        raw = await self._redis.get(f"{TEMP_TOKEN_KEY_PREFIX}{token}")
        if not raw:
            return None
        parsed = json.loads(raw)
        return TempToken(
            token=token,
            kakao_access_token=parsed["kakao_access_token"],
            nickname=parsed.get("nickname"),
            email=parsed.get("email"),
            ttl_seconds=0,
        )
