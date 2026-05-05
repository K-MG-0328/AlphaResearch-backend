import redis.asyncio as aioredis

from app.domains.auth.application.port.out.user_token_store_port import UserTokenStorePort

SESSION_KEY_PREFIX = "session:"


class UserTokenStore(UserTokenStorePort):
    def __init__(self, redis: aioredis.Redis):
        self._redis = redis

    async def save_session(self, token: str, account_id: int, ttl_seconds: int) -> None:
        await self._redis.setex(f"{SESSION_KEY_PREFIX}{token}", ttl_seconds, str(account_id))

    async def save_kakao_access_token(self, account_id: int, kakao_access_token: str, ttl_seconds: int) -> None:
        await self._redis.setex(str(account_id), ttl_seconds, kakao_access_token)
