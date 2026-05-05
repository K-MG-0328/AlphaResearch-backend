from dataclasses import dataclass
from typing import Optional


@dataclass
class TempToken:
    token: str
    kakao_access_token: str
    nickname: Optional[str]
    email: Optional[str]
    ttl_seconds: int = 300  # 5분
