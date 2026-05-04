import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.persistence.base_repository import BaseRepository
from app.domains.news.application.port.saved_article_repository import (
    SavedArticleRepository,
)
from app.domains.news.domain.entity.saved_article import SavedArticle
from app.domains.news.infrastructure.mapper.saved_article_mapper import (
    SavedArticleMapper,
)
from app.domains.news.infrastructure.orm.saved_article_orm import SavedArticleOrm


class SavedArticleRepositoryImpl(
    BaseRepository[SavedArticle, SavedArticleOrm], SavedArticleRepository
):
    _orm_cls = SavedArticleOrm

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    def _to_entity(self, orm: SavedArticleOrm) -> SavedArticle:
        return SavedArticleMapper.to_entity(orm)

    def _to_orm(self, entity: SavedArticle) -> SavedArticleOrm:
        return SavedArticleMapper.to_orm(entity)

    def _default_order_by(self):
        return SavedArticleOrm.saved_at.desc()

    async def find_by_link(self, link: str) -> SavedArticle | None:
        link_hash = hashlib.sha256(link.encode()).hexdigest()
        stmt = select(SavedArticleOrm).where(SavedArticleOrm.link_hash == link_hash)
        result = await self._db.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return SavedArticleMapper.to_entity(orm)

    async def find_all(self, page: int, page_size: int) -> tuple[list[SavedArticle], int]:
        # 포트 시그니처가 page_size 라 base 의 (page, size) 로 위임.
        return await super().find_all(page, page_size)
