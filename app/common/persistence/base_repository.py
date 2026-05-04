"""SQLAlchemy 비동기 Repository 의 공통 베이스.

도메인 Repository 의 39 곳 가까이 같은 ``find_by_*``/``save``/``find_all`` 패턴이
중복되어 있다. 본 베이스는 그 중 가장 흔한 4 가지 — ``find_by_id`` /
``find_all(page, size)`` / ``save`` / ``delete_by_id`` — 를 제네릭으로 제공한다.

서브클래스는 다음만 정의하면 된다:

- ``_orm_cls``: ORM 클래스 (클래스 변수)
- ``_to_entity(orm) -> Entity``: ORM → Domain Entity
- ``_to_orm(entity) -> Orm``: Domain Entity → ORM
- (선택) ``_default_order_by()``: ``find_all`` 의 정렬 컬럼 (기본은 ``_orm_cls.id``)

도메인 특화 메서드(예: ``find_by_email``, ``find_by_link``) 는 서브클래스에 추가.

설계 노트:
- ``find_all`` 의 인자명은 ``(page, size)`` 통일. 기존 포트가 ``page_size`` 등 다른
  이름을 쓴다면 서브클래스가 오버라이드해서 ``super().find_all(page, page_size)``
  로 위임하면 된다.
- ``save`` 는 기존 도메인 패턴을 그대로 따라 ``add → commit → refresh → to_entity``
  순. 트랜잭션 경계가 service 레이어에 있는 경우 서브클래스에서 오버라이드 가능.
- ``delete_by_id`` 는 affected row 수를 bool 로 반환.
"""

from typing import Generic, Optional, Type, TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

Entity = TypeVar("Entity")
Orm = TypeVar("Orm")


class BaseRepository(Generic[Entity, Orm]):
    """비동기 SQLAlchemy + Domain Entity 변환 패턴의 공통 베이스."""

    _orm_cls: Type[Orm]

    def __init__(self, db: AsyncSession):
        self._db = db

    # ── 서브클래스 hooks ───────────────────────────────────────────────────

    def _to_entity(self, orm: Orm) -> Entity:
        raise NotImplementedError

    def _to_orm(self, entity: Entity) -> Orm:
        raise NotImplementedError

    def _default_order_by(self):
        """페이징 조회 시 기본 정렬 컬럼. 서브클래스가 오버라이드 가능."""
        return self._orm_cls.id  # type: ignore[attr-defined]

    # ── 공통 CRUD ─────────────────────────────────────────────────────────

    async def find_by_id(self, id_) -> Optional[Entity]:
        stmt = select(self._orm_cls).where(self._orm_cls.id == id_)  # type: ignore[attr-defined]
        result = await self._db.execute(stmt)
        orm = result.scalar_one_or_none()
        return self._to_entity(orm) if orm else None

    async def find_all(self, page: int, size: int) -> tuple[list[Entity], int]:
        offset = (page - 1) * size
        total_result = await self._db.execute(
            select(func.count()).select_from(self._orm_cls)
        )
        total = total_result.scalar_one()
        result = await self._db.execute(
            select(self._orm_cls)
            .order_by(self._default_order_by())
            .offset(offset)
            .limit(size)
        )
        entities = [self._to_entity(orm) for orm in result.scalars().all()]
        return entities, total

    async def save(self, entity: Entity) -> Entity:
        orm = self._to_orm(entity)
        self._db.add(orm)
        await self._db.commit()
        await self._db.refresh(orm)
        return self._to_entity(orm)

    async def delete_by_id(self, id_) -> bool:
        result = await self._db.execute(
            delete(self._orm_cls).where(self._orm_cls.id == id_)  # type: ignore[attr-defined]
        )
        await self._db.commit()
        return (result.rowcount or 0) > 0
