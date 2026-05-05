import json
from typing import Optional

import redis.asyncio as aioredis

from app.domains.auth.application.port.out.temp_token_query_port import TempTokenQueryPort

TEMP_TOKEN_KEY_PREFIX = "temp_token:"


class TempTokenQueryCacheImpl(TempTokenQueryPort):
    def __init__(self, redis: aioredis.Redis):
        self._redis = redis

    async def find_by_token(self, token: str) -> Optional[dict]:
        raw = await self._redis.get(f"{TEMP_TOKEN_KEY_PREFIX}{token}")
        if not raw:
            return None
        return json.loads(raw)
