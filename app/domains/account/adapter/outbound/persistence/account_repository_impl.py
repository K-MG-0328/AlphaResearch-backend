from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.persistence.base_repository import BaseRepository
from app.domains.account.application.port.out.account_repository_port import AccountRepositoryPort
from app.domains.account.domain.entity.account import Account
from app.domains.account.infrastructure.mapper.account_mapper import AccountMapper
from app.domains.account.infrastructure.orm.account_orm import AccountOrm


class AccountRepositoryImpl(BaseRepository[Account, AccountOrm], AccountRepositoryPort):
    _orm_cls = AccountOrm

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    def _to_entity(self, orm: AccountOrm) -> Account:
        return AccountMapper.to_entity(orm)

    def _to_orm(self, entity: Account) -> AccountOrm:
        return AccountMapper.to_orm(entity)

    async def find_by_email(self, email: str) -> Optional[Account]:
        stmt = select(AccountOrm).where(AccountOrm.email == email)
        result = await self._db.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return AccountMapper.to_entity(orm)
