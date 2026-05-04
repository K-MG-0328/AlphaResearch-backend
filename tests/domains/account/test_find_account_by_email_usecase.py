"""account.FindAccountByEmailUseCase 단위 테스트."""

from typing import Optional

import pytest

from app.domains.account.application.port.out.account_repository_port import AccountRepositoryPort
from app.domains.account.application.usecase.find_account_by_email_usecase import (
    FindAccountByEmailUseCase,
)
from app.domains.account.domain.entity.account import Account

pytestmark = pytest.mark.asyncio


class FakeAccountRepository(AccountRepositoryPort):
    def __init__(self, accounts: Optional[list[Account]] = None):
        self._accounts = list(accounts or [])

    async def find_by_email(self, email: str) -> Optional[Account]:
        return next((a for a in self._accounts if a.email == email), None)

    async def find_by_id(self, account_id: int) -> Optional[Account]:
        return next((a for a in self._accounts if a.account_id == account_id), None)


async def test_returns_unregistered_when_email_is_none():
    usecase = FindAccountByEmailUseCase(FakeAccountRepository())

    response = await usecase.execute(email=None)

    assert response.is_registered is False
    assert response.email is None


async def test_returns_unregistered_when_email_is_empty_string():
    usecase = FindAccountByEmailUseCase(FakeAccountRepository())

    response = await usecase.execute(email="")

    assert response.is_registered is False


async def test_returns_unregistered_with_email_when_account_not_found():
    usecase = FindAccountByEmailUseCase(FakeAccountRepository())

    response = await usecase.execute(email="missing@example.com")

    assert response.is_registered is False
    assert response.email == "missing@example.com"


async def test_returns_account_info_when_found():
    account = Account(account_id=7, email="user@example.com", nickname="nick", kakao_id=12345)
    usecase = FindAccountByEmailUseCase(FakeAccountRepository(accounts=[account]))

    response = await usecase.execute(email="user@example.com")

    assert response.is_registered is True
    assert response.account_id == 7
    assert response.email == "user@example.com"
    assert response.nickname == "nick"
    assert response.kakao_id == 12345
