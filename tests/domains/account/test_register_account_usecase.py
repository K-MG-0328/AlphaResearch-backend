"""account.RegisterAccountUseCase 단위 테스트."""

from typing import Optional

import pytest

from app.common.exception.app_exception import AppException
from app.domains.account.application.port.out.account_repository_port import AccountRepositoryPort
from app.domains.account.application.port.out.temp_token_port import TempTokenInfo, TempTokenPort
from app.domains.account.application.request.register_account_request import (
    RegisterAccountRequest,
)
from app.domains.account.application.usecase.register_account_usecase import (
    RegisterAccountUseCase,
)
from app.domains.account.domain.entity.account import Account

pytestmark = pytest.mark.asyncio


class FakeAccountRepository(AccountRepositoryPort):
    def __init__(self):
        self._next_id = 1
        self.saved: list[Account] = []

    async def find_by_email(self, email: str) -> Optional[Account]:
        return next((a for a in self.saved if a.email == email), None)

    async def find_by_id(self, account_id: int) -> Optional[Account]:
        return next((a for a in self.saved if a.account_id == account_id), None)

    async def save(self, account: Account) -> Account:
        account.account_id = self._next_id
        self._next_id += 1
        self.saved.append(account)
        return account


class FakeTempTokenPort(TempTokenPort):
    def __init__(self, token_data: dict[str, TempTokenInfo] | None = None):
        self._tokens = dict(token_data or {})
        self.deleted: list[str] = []

    async def find_by_token(self, token: str) -> Optional[TempTokenInfo]:
        return self._tokens.get(token)

    async def delete_by_token(self, token: str) -> None:
        self._tokens.pop(token, None)
        self.deleted.append(token)


async def test_raises_401_when_temp_token_invalid():
    repo = FakeAccountRepository()
    temp = FakeTempTokenPort()  # empty
    usecase = RegisterAccountUseCase(repo, temp)

    with pytest.raises(AppException) as exc:
        await usecase.execute(
            token="invalid",
            request=RegisterAccountRequest(nickname="nick", email="e@x.com"),
        )

    assert exc.value.status_code == 401
    assert repo.saved == []


async def test_saves_account_and_deletes_temp_token_on_success():
    repo = FakeAccountRepository()
    temp = FakeTempTokenPort(
        token_data={"valid": TempTokenInfo(nickname="cached", email="cached@x.com")}
    )
    usecase = RegisterAccountUseCase(repo, temp)

    response = await usecase.execute(
        token="valid",
        request=RegisterAccountRequest(nickname="newnick", email="new@x.com"),
    )

    # 저장 + 응답
    assert response.account_id == 1
    assert response.email == "new@x.com"
    assert response.nickname == "newnick"
    assert len(repo.saved) == 1
    # 임시 토큰 정리
    assert temp.deleted == ["valid"]
