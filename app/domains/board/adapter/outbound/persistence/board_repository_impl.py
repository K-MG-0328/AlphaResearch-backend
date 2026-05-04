from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.persistence.base_repository import BaseRepository
from app.domains.board.application.port.out.board_repository_port import BoardRepositoryPort
from app.domains.board.domain.entity.board import Board
from app.domains.board.infrastructure.mapper.board_mapper import BoardMapper
from app.domains.board.infrastructure.orm.board_orm import BoardOrm


class BoardRepositoryImpl(BaseRepository[Board, BoardOrm], BoardRepositoryPort):
    _orm_cls = BoardOrm

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    def _to_entity(self, orm: BoardOrm) -> Board:
        return BoardMapper.to_entity(orm)

    def _to_orm(self, entity: Board) -> BoardOrm:
        return BoardMapper.to_orm(entity)

    def _default_order_by(self):
        return BoardOrm.created_at.desc()

    async def find_paginated(self, page: int, size: int) -> tuple[list[Board], int]:
        # 포트 시그니처 보존 — base 의 find_all(page, size) 위임
        return await super().find_all(page, size)

    async def delete(self, board_id: int) -> None:
        # 포트는 None 반환 — base.delete_by_id 의 bool 반환값을 squash
        await super().delete_by_id(board_id)

    async def update(self, board: Board) -> Board:
        stmt = select(BoardOrm).where(BoardOrm.id == board.board_id)
        result = await self._db.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            raise ValueError(f"Board {board.board_id} not found")
        orm.title = board.title
        orm.content = board.content
        orm.updated_at = datetime.now()
        await self._db.commit()
        await self._db.refresh(orm)
        return BoardMapper.to_entity(orm)
