from typing import Optional

import redis.asyncio as aioredis

from app.domains.account.application.port.out.temp_token_port import TempTokenPort, TempTokenInfo
from app.domains.auth.adapter.outbound.cache.temp_token_store import TempTokenStore


class TempTokenAdapter(TempTokenPort):
    def __init__(self, redis: aioredis.Redis):
        self._store = TempTokenStore(redis)

    async def find_by_token(self, token: str) -> Optional[TempTokenInfo]:
        temp = await self._store.find_by_token(token)
        if temp is None:
            return None
        return TempTokenInfo(nickname=temp.nickname, email=temp.email)

    async def delete_by_token(self, token: str) -> None:
        await self._store.delete_by_token(token)
