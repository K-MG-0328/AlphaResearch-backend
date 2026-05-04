from sqlalchemy.ext.asyncio import AsyncSession

from app.common.persistence.base_repository import BaseRepository
from app.domains.post.application.port.post_repository import PostRepository
from app.domains.post.domain.entity.post import Post
from app.domains.post.infrastructure.mapper.post_mapper import PostMapper
from app.domains.post.infrastructure.orm.post_orm import PostOrm


class PostRepositoryImpl(BaseRepository[Post, PostOrm], PostRepository):
    _orm_cls = PostOrm

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    def _to_entity(self, orm: PostOrm) -> Post:
        return PostMapper.to_entity(orm)

    def _to_orm(self, entity: Post) -> PostOrm:
        return PostMapper.to_orm(entity)

    def _default_order_by(self):
        return PostOrm.created_at.desc()
