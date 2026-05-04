"""board 도메인 5 UseCase 단위 테스트.

Create / GetDetail / GetList / Edit / Delete 의 핵심 path + 권한/존재 체크
edge case 커버.
"""

from datetime import datetime
from typing import Optional

import pytest

from app.common.exception.app_exception import AppException
from app.domains.account.application.port.out.account_repository_port import AccountRepositoryPort
from app.domains.account.domain.entity.account import Account
from app.domains.board.application.port.out.board_repository_port import BoardRepositoryPort
from app.domains.board.application.request.create_board_request import CreateBoardRequest
from app.domains.board.application.request.edit_board_request import EditBoardRequest
from app.domains.board.application.usecase.create_board_usecase import CreateBoardUseCase
from app.domains.board.application.usecase.delete_board_usecase import DeleteBoardUseCase
from app.domains.board.application.usecase.edit_board_usecase import EditBoardUseCase
from app.domains.board.application.usecase.get_board_detail_usecase import (
    GetBoardDetailUseCase,
)
from app.domains.board.application.usecase.get_board_list_usecase import GetBoardListUseCase
from app.domains.board.domain.entity.board import Board

pytestmark = pytest.mark.asyncio


class FakeBoardRepository(BoardRepositoryPort):
    def __init__(self, boards: Optional[list[Board]] = None):
        self._boards: list[Board] = list(boards or [])
        self._next_id = max((b.board_id or 0 for b in self._boards), default=0) + 1
        self.deleted: list[int] = []

    async def find_paginated(self, page: int, size: int) -> tuple[list[Board], int]:
        sorted_boards = sorted(self._boards, key=lambda b: b.created_at, reverse=True)
        offset = (page - 1) * size
        return sorted_boards[offset : offset + size], len(self._boards)

    async def find_by_id(self, board_id: int) -> Optional[Board]:
        return next((b for b in self._boards if b.board_id == board_id), None)

    async def save(self, board: Board) -> Board:
        board.board_id = self._next_id
        self._next_id += 1
        self._boards.append(board)
        return board

    async def update(self, board: Board) -> Board:
        for i, b in enumerate(self._boards):
            if b.board_id == board.board_id:
                self._boards[i] = board
                return board
        raise ValueError(f"Board {board.board_id} not found")

    async def delete(self, board_id: int) -> None:
        self._boards = [b for b in self._boards if b.board_id != board_id]
        self.deleted.append(board_id)


class FakeAccountRepository(AccountRepositoryPort):
    def __init__(self, accounts: Optional[list[Account]] = None):
        self._accounts = list(accounts or [])

    async def find_by_email(self, email: str) -> Optional[Account]:
        return next((a for a in self._accounts if a.email == email), None)

    async def find_by_id(self, account_id: int) -> Optional[Account]:
        return next((a for a in self._accounts if a.account_id == account_id), None)


# ── CreateBoardUseCase ─────────────────────────────────────────────────────


async def test_create_board_includes_account_nickname():
    board_repo = FakeBoardRepository()
    account_repo = FakeAccountRepository(
        accounts=[Account(account_id=1, email="u@x.com", nickname="me", kakao_id=None)]
    )
    usecase = CreateBoardUseCase(board_repo, account_repo)

    response = await usecase.execute(
        CreateBoardRequest(title="t", content="c"), account_id=1
    )

    assert response.board_id == 1
    assert response.title == "t"
    assert response.content == "c"
    assert response.nickname == "me"


async def test_create_board_falls_back_to_unknown_when_account_missing():
    board_repo = FakeBoardRepository()
    usecase = CreateBoardUseCase(board_repo, FakeAccountRepository())

    response = await usecase.execute(
        CreateBoardRequest(title="t", content="c"), account_id=999
    )

    assert response.nickname == "알 수 없음"


# ── GetBoardDetailUseCase ──────────────────────────────────────────────────


async def test_get_detail_raises_404_when_not_found():
    usecase = GetBoardDetailUseCase(FakeBoardRepository(), FakeAccountRepository())

    with pytest.raises(AppException) as exc:
        await usecase.execute(board_id=999)

    assert exc.value.status_code == 404


async def test_get_detail_returns_with_nickname():
    board = Board(
        title="hello", content="world", account_id=1, board_id=10,
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )
    account = Account(account_id=1, email="u@x.com", nickname="auth", kakao_id=None)
    usecase = GetBoardDetailUseCase(
        FakeBoardRepository(boards=[board]), FakeAccountRepository(accounts=[account])
    )

    response = await usecase.execute(board_id=10)

    assert response.board_id == 10
    assert response.title == "hello"
    assert response.nickname == "auth"


# ── GetBoardListUseCase ────────────────────────────────────────────────────


async def test_list_returns_paginated_with_total_pages():
    boards = [
        Board(
            title=f"t{i}", content="c", account_id=1, board_id=i,
            created_at=datetime(2026, 1, i + 1),
            updated_at=datetime(2026, 1, i + 1),
        )
        for i in range(5)
    ]
    account = Account(account_id=1, email="u@x.com", nickname="u", kakao_id=None)
    usecase = GetBoardListUseCase(
        FakeBoardRepository(boards=boards), FakeAccountRepository(accounts=[account])
    )

    response = await usecase.execute(page=1, size=2)

    assert response.total_count == 5
    assert response.total_pages == 3  # ceil(5/2)
    assert response.page == 1
    assert len(response.boards) == 2
    # 최신순(created_at desc) — i=4 가 가장 최신
    assert response.boards[0].title == "t4"


async def test_list_returns_empty_when_no_boards():
    usecase = GetBoardListUseCase(FakeBoardRepository(), FakeAccountRepository())

    response = await usecase.execute(page=1, size=10)

    assert response.total_count == 0
    assert response.total_pages == 0
    assert response.boards == []


# ── EditBoardUseCase ───────────────────────────────────────────────────────


async def test_edit_raises_404_when_board_missing():
    usecase = EditBoardUseCase(FakeBoardRepository())

    with pytest.raises(AppException) as exc:
        await usecase.execute(
            board_id=999, account_id=1, nickname="me",
            request=EditBoardRequest(title="t", content="c"),
        )

    assert exc.value.status_code == 404


async def test_edit_raises_403_when_not_owner():
    board = Board(title="t", content="c", account_id=999, board_id=1)
    usecase = EditBoardUseCase(FakeBoardRepository(boards=[board]))

    with pytest.raises(AppException) as exc:
        await usecase.execute(
            board_id=1, account_id=1, nickname="me",
            request=EditBoardRequest(title="new", content="new"),
        )

    assert exc.value.status_code == 403


async def test_edit_updates_when_owner():
    board = Board(title="old", content="old", account_id=1, board_id=1)
    repo = FakeBoardRepository(boards=[board])
    usecase = EditBoardUseCase(repo)

    response = await usecase.execute(
        board_id=1, account_id=1, nickname="me",
        request=EditBoardRequest(title="newtitle", content="newcontent"),
    )

    assert response.title == "newtitle"
    assert response.content == "newcontent"
    assert response.nickname == "me"


# ── DeleteBoardUseCase ─────────────────────────────────────────────────────


async def test_delete_raises_404_when_missing():
    usecase = DeleteBoardUseCase(FakeBoardRepository())

    with pytest.raises(AppException) as exc:
        await usecase.execute(board_id=999, account_id=1)

    assert exc.value.status_code == 404


async def test_delete_raises_403_when_not_owner():
    board = Board(title="t", content="c", account_id=999, board_id=1)
    usecase = DeleteBoardUseCase(FakeBoardRepository(boards=[board]))

    with pytest.raises(AppException) as exc:
        await usecase.execute(board_id=1, account_id=1)

    assert exc.value.status_code == 403


async def test_delete_removes_when_owner():
    board = Board(title="t", content="c", account_id=1, board_id=1)
    repo = FakeBoardRepository(boards=[board])
    usecase = DeleteBoardUseCase(repo)

    await usecase.execute(board_id=1, account_id=1)

    assert repo.deleted == [1]
