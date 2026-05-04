"""account.CreateAccountUseCase 단위 테스트."""

from typing import Optional

import pytest

from app.common.exception.app_exception import AppException
from app.domains.account.application.port.out.account_save_port import AccountSavePort
from app.domains.account.application.port.out.account_token_cache_port import (
    AccountTokenCachePort,
)
from app.domains.account.application.port.out.temp_token_port import TempTokenPort
from app.domains.account.application.usecase.create_account_usecase import CreateAccountUseCase
from app.domains.account.domain.entity.account import Account


pytestmark = pytest.mark.asyncio


class _TempTokenData:
    """temp_token_port.find_by_token 이 반환하는 객체 — kakao_access_token 속성 보유."""

    def __init__(self, kakao_access_token: str):
        self.kakao_access_token = kakao_access_token


class FakeAccountSavePort(AccountSavePort):
    def __init__(self):
        self.saved: list[Account] = []

    async def save(self, account: Account) -> Account:
        account.account_id = 200
        self.saved.append(account)
        return account


class FakeTempTokenPort(TempTokenPort):
    def __init__(self, token_map: dict[str, object]):
        self._tokens = dict(token_map)
        self.deleted: list[str] = []

    async def find_by_token(self, token: str) -> Optional[object]:
        return self._tokens.get(token)

    async def delete_by_token(self, token: str) -> None:
        self._tokens.pop(token, None)
        self.deleted.append(token)


class FakeAccountTokenCachePort(AccountTokenCachePort):
    def __init__(self):
        self.kakao_saves: list[tuple[int, str]] = []
        self.issued_tokens: list[int] = []

    async def save_kakao_token(self, account_id: int, kakao_access_token: str) -> None:
        self.kakao_saves.append((account_id, kakao_access_token))

    async def issue_user_token(self, account_id: int) -> str:
        self.issued_tokens.append(account_id)
        return f"user-token-{account_id}"


async def test_raises_401_when_temp_token_invalid():
    save_port = FakeAccountSavePort()
    cache = FakeAccountTokenCachePort()
    usecase = CreateAccountUseCase(save_port, FakeTempTokenPort({}), cache)

    with pytest.raises(AppException) as exc:
        await usecase.execute(nickname="n", email="e@x.com", temp_token_value="invalid")

    assert exc.value.status_code == 401
    # 계정도 저장되지 않고 토큰도 발행되지 않아야 함
    assert save_port.saved == []
    assert cache.issued_tokens == []


async def test_saves_account_caches_kakao_token_and_issues_user_token():
    save_port = FakeAccountSavePort()
    temp = FakeTempTokenPort({"valid": _TempTokenData(kakao_access_token="kakao-abc")})
    cache = FakeAccountTokenCachePort()
    usecase = CreateAccountUseCase(save_port, temp, cache)

    response = await usecase.execute(
        nickname="newbie", email="new@x.com", temp_token_value="valid"
    )

    assert response.account_id == 200
    assert response.email == "new@x.com"
    assert response.nickname == "newbie"
    assert response.user_token == "user-token-200"
    # 임시 토큰 정리
    assert temp.deleted == ["valid"]
    # 카카오 토큰 캐시 + 유저 토큰 발행
    assert cache.kakao_saves == [(200, "kakao-abc")]
    assert cache.issued_tokens == [200]
