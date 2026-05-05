from typing import Optional

import redis.asyncio as aioredis

from app.domains.auth.application.port.out.session_query_port import SessionQueryPort

SESSION_KEY_PREFIX = "session:"


class SessionQueryCacheImpl(SessionQueryPort):
    def __init__(self, redis: aioredis.Redis):
        self._redis = redis

    async def get_account_id_by_session(self, token: str) -> Optional[int]:
        raw = await self._redis.get(f"{SESSION_KEY_PREFIX}{token}")
        if not raw:
            return None
        return int(raw)
