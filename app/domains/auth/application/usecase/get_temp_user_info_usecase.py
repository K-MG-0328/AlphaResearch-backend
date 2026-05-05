from app.common.exception.app_exception import AppException
from app.domains.auth.application.port.out.account_info_query_port import AccountInfoQueryPort
from app.domains.auth.application.port.out.session_query_port import SessionQueryPort
from app.domains.auth.application.port.out.temp_token_query_port import TempTokenQueryPort
from app.domains.auth.application.response.temp_user_info_response import TempUserInfoResponse


class GetTempUserInfoUseCase:
    def __init__(
        self,
        temp_token_query_port: TempTokenQueryPort,
        session_query_port: SessionQueryPort,
        account_info_query_port: AccountInfoQueryPort,
    ):
        self._temp_token_query_port = temp_token_query_port
        self._session_query_port = session_query_port
        self._account_info_query_port = account_info_query_port

    async def execute(self, token: str) -> TempUserInfoResponse:
        # 임시 토큰(temp_token) 확인
        temp_data = await self._temp_token_query_port.find_by_token(token)
        if temp_data:
            nickname = temp_data.get("nickname")
            email = temp_data.get("email")
            return TempUserInfoResponse(
                is_registered=False,
                nickname=nickname,
                email=email,
            )

        # 세션 토큰(user_token) 확인
        account_id = await self._session_query_port.get_account_id_by_session(token)
        if account_id:
            account = await self._account_info_query_port.find_by_id(account_id)
            if account:
                return TempUserInfoResponse(
                    is_registered=True,
                    nickname=account.nickname,
                    email=account.email,
                )

        raise AppException(status_code=401, message="유효하지 않거나 만료된 토큰입니다.")
