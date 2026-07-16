from pydantic import BaseModel


class GoogleLoginRequest(BaseModel):
    id_token: str
    invite_uid: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AdminUserSummary(BaseModel):
    id: str
    email: str
    name: str | None
    is_staff: bool


class AdminLoginResponse(BaseModel):
    access_token: str
    user: AdminUserSummary
