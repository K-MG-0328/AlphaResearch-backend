from enum import Enum
from typing import Optional

from pydantic import BaseModel


class TokenType(str, Enum):
    TEMP = "TEMP"
    REGULAR = "REGULAR"


class KakaoCallbackResponse(BaseModel):
    token_type: TokenType
    is_registered: bool
    nickname: Optional[str] = None
    email: Optional[str] = None
    account_id: Optional[int] = None
