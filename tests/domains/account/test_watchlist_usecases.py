"""account 도메인 watchlist 4 UseCase 단위 테스트.

Add / Remove / Update / Get 각 UseCase 의 핵심 path + edge case 커버.
"""

from typing import Optional

import pytest

from app.common.exception.app_exception import AppException
from app.domains.account.application.exception.watchlist_exceptions import (
    DuplicateWatchlistStockException,
    WatchlistStockNotFoundException,
)
from app.domains.account.application.port.out.stock_master_port import StockMasterPort
from app.domains.account.application.port.out.watchlist_repository_port import (
    WatchlistRepositoryPort,
)
from app.domains.account.application.usecase.add_watchlist_stock_usecase import (
    AddWatchlistStockUseCase,
)
from app.domains.account.application.usecase.get_watchlist_usecase import GetWatchlistUseCase
from app.domains.account.application.usecase.remove_watchlist_stock_usecase import (
    RemoveWatchlistStockUseCase,
)
from app.domains.account.application.usecase.update_watchlist_stock_usecase import (
    UpdateWatchlistStockUseCase,
)
from app.domains.account.domain.entity.watchlist_item import WatchlistItem
from app.domains.account.domain.entity.watchlist_with_theme_item import WatchlistWithThemeItem

pytestmark = pytest.mark.asyncio


class FakeWatchlistRepository(WatchlistRepositoryPort):
    """In-memory watchlist. (account_id, stock_code) → stock_name 키로 보관."""

    def __init__(
        self,
        items: Optional[dict[tuple[int, str], WatchlistItem]] = None,
        themed: Optional[dict[int, list[WatchlistWithThemeItem]]] = None,
    ):
        self._items = dict(items or {})
        self._themed = dict(themed or {})
        self.added: list[tuple[int, WatchlistItem]] = []
        self.removed: list[tuple[int, str]] = []
        self.replaced: list[tuple[int, str, WatchlistItem]] = []

    async def add(self, account_id: int, item: WatchlistItem) -> None:
        self._items[(account_id, item.stock_code)] = item
        self.added.append((account_id, item))

    async def find_all_by_account(self, account_id: int) -> list[WatchlistItem]:
        return [v for (a, _), v in self._items.items() if a == account_id]

    async def find_all_with_theme_by_account(
        self, account_id: int
    ) -> list[WatchlistWithThemeItem]:
        return list(self._themed.get(account_id, []))

    async def exists(self, account_id: int, stock_code: str) -> bool:
        return (account_id, stock_code) in self._items

    async def exists_for_any_user(self, stock_code: str) -> bool:
        return any(code == stock_code for _, code in self._items.keys())

    async def remove(self, account_id: int, stock_code: str) -> None:
        self._items.pop((account_id, stock_code), None)
        self.removed.append((account_id, stock_code))

    async def replace(
        self, account_id: int, old_code: str, new_item: WatchlistItem
    ) -> None:
        self._items.pop((account_id, old_code), None)
        self._items[(account_id, new_item.stock_code)] = new_item
        self.replaced.append((account_id, old_code, new_item))


class FakeStockMasterPort(StockMasterPort):
    def __init__(self, items: list[WatchlistItem]):
        self._items = items

    async def find_by_codes(self, codes: list[str]) -> list[WatchlistItem]:
        return [it for it in self._items if it.stock_code in codes]


# ── AddWatchlistStockUseCase ──────────────────────────────────────────────


async def test_add_raises_404_when_stock_code_not_in_master():
    repo = FakeWatchlistRepository()
    usecase = AddWatchlistStockUseCase(repo, FakeStockMasterPort(items=[]))

    with pytest.raises(AppException) as exc:
        await usecase.execute(account_id=1, stock_code="MISSING")

    assert exc.value.status_code == 404
    assert repo.added == []


async def test_add_raises_409_when_already_in_watchlist():
    existing = WatchlistItem(stock_code="005930", stock_name="삼성전자")
    repo = FakeWatchlistRepository(items={(1, "005930"): existing})
    master = FakeStockMasterPort(items=[existing])
    usecase = AddWatchlistStockUseCase(repo, master)

    with pytest.raises(DuplicateWatchlistStockException) as exc:
        await usecase.execute(account_id=1, stock_code="005930")

    assert exc.value.status_code == 409


async def test_add_inserts_and_returns_full_watchlist():
    repo = FakeWatchlistRepository(
        items={(1, "000660"): WatchlistItem(stock_code="000660", stock_name="SK하이닉스")}
    )
    master = FakeStockMasterPort(
        items=[WatchlistItem(stock_code="005930", stock_name="삼성전자")]
    )
    usecase = AddWatchlistStockUseCase(repo, master)

    response = await usecase.execute(account_id=1, stock_code="005930")

    assert len(repo.added) == 1
    codes = {s.code for s in response.stocks}
    assert codes == {"005930", "000660"}


# ── RemoveWatchlistStockUseCase ───────────────────────────────────────────


async def test_remove_raises_404_when_not_in_user_and_no_other_user():
    repo = FakeWatchlistRepository()
    usecase = RemoveWatchlistStockUseCase(repo)

    with pytest.raises(WatchlistStockNotFoundException) as exc:
        await usecase.execute(account_id=1, stock_code="MISSING")

    assert exc.value.status_code == 404


async def test_remove_raises_403_when_other_user_owns_the_stock():
    repo = FakeWatchlistRepository(
        items={(2, "005930"): WatchlistItem(stock_code="005930", stock_name="삼성전자")}
    )
    usecase = RemoveWatchlistStockUseCase(repo)

    with pytest.raises(AppException) as exc:
        await usecase.execute(account_id=1, stock_code="005930")

    assert exc.value.status_code == 403


async def test_remove_deletes_when_user_owns():
    repo = FakeWatchlistRepository(
        items={(1, "005930"): WatchlistItem(stock_code="005930", stock_name="삼성전자")}
    )
    usecase = RemoveWatchlistStockUseCase(repo)

    await usecase.execute(account_id=1, stock_code="005930")

    assert repo.removed == [(1, "005930")]


# ── UpdateWatchlistStockUseCase ───────────────────────────────────────────


async def test_update_raises_404_when_old_not_in_watchlist():
    repo = FakeWatchlistRepository()
    master = FakeStockMasterPort(
        items=[WatchlistItem(stock_code="005930", stock_name="삼성전자")]
    )
    usecase = UpdateWatchlistStockUseCase(repo, master)

    with pytest.raises(WatchlistStockNotFoundException):
        await usecase.execute(account_id=1, old_stock_code="000660", new_stock_code="005930")


async def test_update_raises_404_when_new_not_in_master():
    existing = WatchlistItem(stock_code="000660", stock_name="SK하이닉스")
    repo = FakeWatchlistRepository(items={(1, "000660"): existing})
    usecase = UpdateWatchlistStockUseCase(repo, FakeStockMasterPort(items=[]))

    with pytest.raises(AppException) as exc:
        await usecase.execute(account_id=1, old_stock_code="000660", new_stock_code="MISSING")

    assert exc.value.status_code == 404


async def test_update_raises_409_when_new_already_in_watchlist():
    items = {
        (1, "000660"): WatchlistItem(stock_code="000660", stock_name="SK하이닉스"),
        (1, "005930"): WatchlistItem(stock_code="005930", stock_name="삼성전자"),
    }
    repo = FakeWatchlistRepository(items=items)
    master = FakeStockMasterPort(
        items=[WatchlistItem(stock_code="005930", stock_name="삼성전자")]
    )
    usecase = UpdateWatchlistStockUseCase(repo, master)

    with pytest.raises(DuplicateWatchlistStockException):
        await usecase.execute(account_id=1, old_stock_code="000660", new_stock_code="005930")


async def test_update_replaces_and_returns_themed_list():
    repo = FakeWatchlistRepository(
        items={(1, "000660"): WatchlistItem(stock_code="000660", stock_name="SK하이닉스")},
        themed={
            1: [WatchlistWithThemeItem(stock_code="005930", stock_name="삼성전자", theme_name="반도체")]
        },
    )
    master = FakeStockMasterPort(
        items=[WatchlistItem(stock_code="005930", stock_name="삼성전자")]
    )
    usecase = UpdateWatchlistStockUseCase(repo, master)

    response = await usecase.execute(
        account_id=1, old_stock_code="000660", new_stock_code="005930"
    )

    assert repo.replaced == [
        (1, "000660", WatchlistItem(stock_code="005930", stock_name="삼성전자"))
    ]
    assert len(response.stocks) == 1
    assert response.stocks[0].stock_code == "005930"
    assert response.stocks[0].theme_name == "반도체"


# ── GetWatchlistUseCase ───────────────────────────────────────────────────


async def test_get_returns_empty_when_no_items():
    repo = FakeWatchlistRepository()
    usecase = GetWatchlistUseCase(repo)

    response = await usecase.execute(account_id=1)

    assert response.stocks == []


async def test_get_returns_items_with_theme():
    repo = FakeWatchlistRepository(
        themed={
            1: [
                WatchlistWithThemeItem(stock_code="005930", stock_name="삼성전자", theme_name="반도체"),
                WatchlistWithThemeItem(stock_code="000660", stock_name="SK하이닉스", theme_name="반도체"),
            ]
        }
    )
    usecase = GetWatchlistUseCase(repo)

    response = await usecase.execute(account_id=1)

    assert len(response.stocks) == 2
    codes = [s.stock_code for s in response.stocks]
    assert codes == ["005930", "000660"]
    assert all(s.theme_name == "반도체" for s in response.stocks)
