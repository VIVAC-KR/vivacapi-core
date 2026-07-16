from pydantic import BaseModel, ConfigDict


class GoogleLoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"id_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6..."}}
    )

    id_token: str
    invite_uid: str | None = None


class TokenResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
            }
        }
    )

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}
        }
    )

    refresh_token: str


class AdminUserSummary(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "j3kD9fQxT2mZ8pR1yN6vXa",
                "email": "staff@vivac.kr",
                "name": "김스태프",
                "is_staff": True,
            }
        }
    )

    id: str
    email: str
    name: str | None
    is_staff: bool


class AdminLoginResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "user": {
                    "id": "j3kD9fQxT2mZ8pR1yN6vXa",
                    "email": "staff@vivac.kr",
                    "name": "김스태프",
                    "is_staff": True,
                },
            }
        }
    )

    access_token: str
    user: AdminUserSummary
