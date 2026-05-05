"""authentication.GetAuthMeUseCase 단위 테스트.

3 분기 커버:
- temp_token 발견 → tokenType=TEMPORARY
- session_token + account 발견 → tokenType=PERMANENT
- 모두 없음 → AppException 401
"""

from typing import Optional

import pytest

from app.common.exception.app_exception import AppException
from app.domains.auth.application.port.out.account_info_query_port import (
    AccountInfo,
    AccountInfoQueryPort,
)
from app.domains.auth.application.port.out.session_query_port import SessionQueryPort
from app.domains.auth.application.port.out.temp_token_query_port import (
    TempTokenQueryPort,
)
from app.domains.auth.application.usecase.get_auth_me_usecase import GetAuthMeUseCase

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


async def test_returns_temporary_when_temp_token_match():
    usecase = GetAuthMeUseCase(
        FakeTempTokenQueryPort(data={"email": "temp@x.com", "nickname": "tnick"}),
        FakeSessionQueryPort(),
        FakeAccountInfoQueryPort(),
    )

    response = await usecase.execute(token="temp-token-1")

    assert response.tokenType == "TEMPORARY"
    assert response.user.email == "temp@x.com"
    assert response.user.nickname == "tnick"
    assert response.user.id == ""


async def test_returns_temporary_with_empty_strings_when_temp_data_missing_fields():
    """temp_data 에 email/nickname 키가 없어도 ``or ""`` fallback 으로 빈 문자열 반환."""
    # 빈 dict 은 falsy 라 temp 분기를 trigger 하지 않음 → truthy 한 채로 키만 누락된 형태로 검증.
    usecase = GetAuthMeUseCase(
        FakeTempTokenQueryPort(data={"unrelated": "value"}),
        FakeSessionQueryPort(),
        FakeAccountInfoQueryPort(),
    )

    response = await usecase.execute(token="temp-partial")

    assert response.tokenType == "TEMPORARY"
    assert response.user.email == ""
    assert response.user.nickname == ""


async def test_returns_permanent_when_session_resolves_to_account():
    account = AccountInfo(account_id=42, email="user@x.com", nickname="real-nick")
    usecase = GetAuthMeUseCase(
        FakeTempTokenQueryPort(),
        FakeSessionQueryPort(account_id=42),
        FakeAccountInfoQueryPort(account=account),
    )

    response = await usecase.execute(token="session-token")

    assert response.tokenType == "PERMANENT"
    assert response.user.id == "42"
    assert response.user.email == "user@x.com"
    assert response.user.nickname == "real-nick"


async def test_returns_permanent_with_empty_nickname_when_account_has_no_nickname():
    account = AccountInfo(account_id=43, email="anon@x.com", nickname=None)
    usecase = GetAuthMeUseCase(
        FakeTempTokenQueryPort(),
        FakeSessionQueryPort(account_id=43),
        FakeAccountInfoQueryPort(account=account),
    )

    response = await usecase.execute(token="session-token")

    assert response.tokenType == "PERMANENT"
    assert response.user.nickname == ""


async def test_raises_401_when_no_temp_no_session():
    usecase = GetAuthMeUseCase(
        FakeTempTokenQueryPort(),
        FakeSessionQueryPort(),
        FakeAccountInfoQueryPort(),
    )

    with pytest.raises(AppException) as exc:
        await usecase.execute(token="garbage")

    assert exc.value.status_code == 401


async def test_raises_401_when_session_account_not_found():
    """세션은 account_id 를 반환했지만 account_info_query 에서 못 찾는 경우."""
    usecase = GetAuthMeUseCase(
        FakeTempTokenQueryPort(),
        FakeSessionQueryPort(account_id=999),
        FakeAccountInfoQueryPort(),  # account 없음
    )

    with pytest.raises(AppException) as exc:
        await usecase.execute(token="session-orphan")

    assert exc.value.status_code == 401
