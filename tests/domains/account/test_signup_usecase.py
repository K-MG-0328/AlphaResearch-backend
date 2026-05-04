"""account.SignupUseCase 단위 테스트."""

from typing import Optional

import pytest

from app.common.exception.app_exception import AppException
from app.domains.account.application.port.out.account_repository_port import AccountRepositoryPort
from app.domains.account.application.port.out.account_save_port import AccountSavePort
from app.domains.account.application.port.out.stock_master_port import StockMasterPort
from app.domains.account.application.port.out.watchlist_save_port import WatchlistSavePort
from app.domains.account.application.request.signup_request import SignupRequest
from app.domains.account.application.usecase.signup_usecase import SignupUseCase
from app.domains.account.domain.entity.account import Account
from app.domains.account.domain.entity.watchlist_item import WatchlistItem

pytestmark = pytest.mark.asyncio


class FakeAccountRepository(AccountRepositoryPort):
    def __init__(self, accounts: Optional[list[Account]] = None):
        self._accounts = list(accounts or [])

    async def find_by_email(self, email: str) -> Optional[Account]:
        return next((a for a in self._accounts if a.email == email), None)

    async def find_by_id(self, account_id: int) -> Optional[Account]:
        return next((a for a in self._accounts if a.account_id == account_id), None)


class FakeAccountSavePort(AccountSavePort):
    def __init__(self):
        self._next_id = 100
        self.saved: list[Account] = []

    async def save(self, account: Account) -> Account:
        account.account_id = self._next_id
        self._next_id += 1
        self.saved.append(account)
        return account


class FakeStockMasterPort(StockMasterPort):
    def __init__(self, items: list[WatchlistItem]):
        self._items = items

    async def find_by_codes(self, codes: list[str]) -> list[WatchlistItem]:
        return [it for it in self._items if it.stock_code in codes]


class FakeWatchlistSavePort(WatchlistSavePort):
    def __init__(self):
        self.saved: list[tuple[int, list[WatchlistItem]]] = []

    async def save_all(self, account_id: int, items: list[WatchlistItem]) -> list[WatchlistItem]:
        self.saved.append((account_id, items))
        return items


async def test_raises_409_when_email_already_exists():
    existing = Account(account_id=1, email="taken@x.com", nickname="x", kakao_id=None)
    usecase = SignupUseCase(
        FakeAccountRepository(accounts=[existing]),
        FakeAccountSavePort(),
        FakeStockMasterPort(items=[]),
        FakeWatchlistSavePort(),
    )

    with pytest.raises(AppException) as exc:
        await usecase.execute(
            SignupRequest(nickname="n", email="taken@x.com", watchlist=None),
        )

    assert exc.value.status_code == 409


async def test_raises_400_when_watchlist_codes_invalid():
    save_port = FakeAccountSavePort()
    usecase = SignupUseCase(
        FakeAccountRepository(),
        save_port,
        FakeStockMasterPort(items=[WatchlistItem(stock_code="005930", stock_name="삼성전자")]),
        FakeWatchlistSavePort(),
    )

    with pytest.raises(AppException) as exc:
        await usecase.execute(
            SignupRequest(nickname="n", email="new@x.com", watchlist=["005930", "INVALID"]),
        )

    assert exc.value.status_code == 400
    # 검증 실패 시 계정도 저장되지 않아야 함
    assert save_port.saved == []


async def test_signs_up_with_watchlist_when_all_codes_valid():
    save_port = FakeAccountSavePort()
    watchlist_save_port = FakeWatchlistSavePort()
    usecase = SignupUseCase(
        FakeAccountRepository(),
        save_port,
        FakeStockMasterPort(
            items=[
                WatchlistItem(stock_code="005930", stock_name="삼성전자"),
                WatchlistItem(stock_code="000660", stock_name="SK하이닉스"),
            ]
        ),
        watchlist_save_port,
    )

    response = await usecase.execute(
        SignupRequest(
            nickname="nick",
            email="new@x.com",
            watchlist=["005930", "000660", "005930"],  # 중복 입력 → 자동 제거
        ),
    )

    assert response.account_id == 100
    assert response.email == "new@x.com"
    assert response.nickname == "nick"
    assert [w.code for w in response.watchlist] == ["005930", "000660"]
    # 1 계정 저장 + 1 watchlist 저장
    assert len(save_port.saved) == 1
    assert len(watchlist_save_port.saved) == 1
    assert watchlist_save_port.saved[0][0] == 100  # account_id


async def test_signs_up_without_watchlist():
    save_port = FakeAccountSavePort()
    watchlist_save_port = FakeWatchlistSavePort()
    usecase = SignupUseCase(
        FakeAccountRepository(),
        save_port,
        FakeStockMasterPort(items=[]),
        watchlist_save_port,
    )

    response = await usecase.execute(
        SignupRequest(nickname="solo", email="solo@x.com", watchlist=None),
    )

    assert response.account_id == 100
    assert response.watchlist == []
    # watchlist 가 없으면 save_all 호출도 없어야 함
    assert watchlist_save_port.saved == []
