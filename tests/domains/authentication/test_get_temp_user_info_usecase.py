"""authentication.GetTempUserInfoUseCase 단위 테스트.

GetAuthMeUseCase 와 비슷한 분기 구조이지만 응답 모델이 다름:
- temp_token 발견 → is_registered=False + nickname/email
- session_token + account 발견 → is_registered=True + nickname/email
- 모두 없음 → AppException 401
"""

from typing import Optional

import pytest

from app.common.exception.app_exception import AppException
from app.domains.authentication.application.port.out.account_info_query_port import (
    AccountInfo,
    AccountInfoQueryPort,
)
from app.domains.authentication.application.port.out.session_query_port import SessionQueryPort
from app.domains.authentication.application.port.out.temp_token_query_port import (
    TempTokenQueryPort,
)
from app.domains.authentication.application.usecase.get_temp_user_info_usecase import (
    GetTempUserInfoUseCase,
)

pytestmark = pytest.mark.asyncio


class FakeTempTokenQueryPort(TempTokenQueryPort):
    def __init__(self, data: Optional[dict] = None):
        self._data = data

    async def find_by_token(self, token: str) -> Optional[dict]:
        return self._data


class FakeSessionQueryPort(SessionQueryPort):
    def __init__(self, account_id: Optional[int] = None):
        self._account_id = account_id

    async def get_account_id_by_session(self, token: str) -> Optional[int]:
        return self._account_id


class FakeAccountInfoQueryPort(AccountInfoQueryPort):
    def __init__(self, account: Optional[AccountInfo] = None):
        self._account = account

    async def find_by_id(self, account_id: int) -> Optional[AccountInfo]:
        if self._account and self._account.account_id == account_id:
            return self._account
        return None


async def test_returns_unregistered_when_temp_token_found():
    usecase = GetTempUserInfoUseCase(
        FakeTempTokenQueryPort(data={"nickname": "tempnick", "email": "temp@x.com"}),
        FakeSessionQueryPort(),
        FakeAccountInfoQueryPort(),
    )

    response = await usecase.execute(token="temp-token")

    assert response.is_registered is False
    assert response.nickname == "tempnick"
    assert response.email == "temp@x.com"


async def test_returns_registered_when_session_resolves_to_account():
    account = AccountInfo(account_id=10, email="real@x.com", nickname="real")
    usecase = GetTempUserInfoUseCase(
        FakeTempTokenQueryPort(),
        FakeSessionQueryPort(account_id=10),
        FakeAccountInfoQueryPort(account=account),
    )

    response = await usecase.execute(token="session-token")

    assert response.is_registered is True
    assert response.nickname == "real"
    assert response.email == "real@x.com"


async def test_raises_401_when_neither_temp_nor_session():
    usecase = GetTempUserInfoUseCase(
        FakeTempTokenQueryPort(),
        FakeSessionQueryPort(),
        FakeAccountInfoQueryPort(),
    )

    with pytest.raises(AppException) as exc:
        await usecase.execute(token="garbage")

    assert exc.value.status_code == 401


async def test_raises_401_when_session_account_missing():
    """세션은 valid 지만 account_info 가 없는 케이스."""
    usecase = GetTempUserInfoUseCase(
        FakeTempTokenQueryPort(),
        FakeSessionQueryPort(account_id=999),
        FakeAccountInfoQueryPort(),
    )

    with pytest.raises(AppException) as exc:
        await usecase.execute(token="orphan")

    assert exc.value.status_code == 401
