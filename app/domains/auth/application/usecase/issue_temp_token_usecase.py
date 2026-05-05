import uuid
from typing import Optional

from app.domains.auth.application.port.out.temp_token_store_port import TempTokenStorePort
from app.domains.auth.domain.entity.temp_token import TempToken

TEMP_TOKEN_TTL_SECONDS = 300  # 5분


class IssueTempTokenUseCase:
    def __init__(self, temp_token_store: TempTokenStorePort):
        self._store = temp_token_store

    async def execute(
        self,
        kakao_access_token: str,
        nickname: Optional[str],
        email: Optional[str],
    ) -> TempToken:
        token = str(uuid.uuid4())
        temp_token = TempToken(
            token=token,
            kakao_access_token=kakao_access_token,
            nickname=nickname,
            email=email,
            ttl_seconds=TEMP_TOKEN_TTL_SECONDS,
        )
        await self._store.save(temp_token)
        return temp_token
