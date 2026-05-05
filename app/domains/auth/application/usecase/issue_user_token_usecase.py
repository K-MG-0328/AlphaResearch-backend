import uuid

from app.domains.auth.application.port.out.user_token_store_port import UserTokenStorePort


class IssueUserTokenUseCase:
    def __init__(self, user_token_store: UserTokenStorePort, ttl_seconds: int):
        self._store = user_token_store
        self._ttl_seconds = ttl_seconds

    async def execute(self, account_id: int, kakao_access_token: str) -> str:
        token = str(uuid.uuid4())
        await self._store.save_session(token, account_id, self._ttl_seconds)
        await self._store.save_kakao_access_token(account_id, kakao_access_token, self._ttl_seconds)
        return token
