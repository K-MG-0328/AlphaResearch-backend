from typing import Literal

from pydantic import BaseModel


class AuthUser(BaseModel):
    id: str
    email: str
    nickname: str


class AuthMeResponse(BaseModel):
    tokenType: Literal["TEMPORARY", "PERMANENT"]
    user: AuthUser
