from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.account.infrastructure.orm.account_orm import AccountOrm
from app.domains.auth.application.port.out.account_info_query_port import AccountInfo, AccountInfoQueryPort


class AccountInfoQueryImpl(AccountInfoQueryPort):
    def __init__(self, db: AsyncSession):
        self._db = db

    async def find_by_id(self, account_id: int) -> Optional[AccountInfo]:
        stmt = select(AccountOrm).where(AccountOrm.id == account_id)
        result = await self._db.execute(stmt)
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        return AccountInfo(
            account_id=orm.id,
            email=orm.email,
            nickname=orm.nickname,
        )
