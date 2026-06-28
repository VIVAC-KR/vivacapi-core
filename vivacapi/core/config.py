from typing import Literal

from pydantic import computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # -------------------------------------------------------------------------
    # 애플리케이션
    # -------------------------------------------------------------------------
    ENVIRONMENT: Literal["local", "dev", "prod"] = "local"

    # -------------------------------------------------------------------------
    # 데이터베이스
    # local: docker-compose / dev·prod: RDS 프라이빗 엔드포인트 (VPC 직접 접속)
    # -------------------------------------------------------------------------
    DB_HOST: str = "localhost"
    DB_PORT: str = "5432"
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str

    # -------------------------------------------------------------------------
    # Google OAuth 2.0
    # -------------------------------------------------------------------------
    GOOGLE_CLIENT_ID: str

    # vivac-console(어드민) 로그인 시 허용할 이메일 도메인.
    # 미설정이면 도메인 제한 없음.
    ALLOWED_EMAIL_DOMAIN: str | None = None

    # -------------------------------------------------------------------------
    # JWT
    # -------------------------------------------------------------------------
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: str = "30"
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: str = "7"
    JWT_ADMIN_ACCESS_TOKEN_EXPIRE_HOURS: str = "8"

    # -------------------------------------------------------------------------
    # SQLAdmin (/admin) 세션
    # SessionMiddleware의 서명/암호화 키. JWT_SECRET_KEY와 분리해
    # 어드민 세션 노출 시 토큰 발급키 유출까지 번지지 않도록 한다.
    # -------------------------------------------------------------------------
    ADMIN_SESSION_SECRET: str

    # -------------------------------------------------------------------------
    # CORS
    # 콤마 구분 문자열로 받아 list[str]로 파싱.
    # 미설정 시 local만 localhost:3000/127.0.0.1:3000을 디폴트로 주입.
    # dev/prod는 비어 있는 디폴트 → 환경 변수에서 반드시 명시.
    # -------------------------------------------------------------------------
    CORS_ALLOWED_ORIGINS: list[str] | None = None

    # -------------------------------------------------------------------------
    # 이미지 스토리지 (S3 + CloudFront)
    # 미설정(None) 시 이미지 업로드/조회 API는 503을 반환한다.
    # S3_ENDPOINT_URL은 로컬 테스트(MinIO 등)에서만 사용.
    # -------------------------------------------------------------------------
    AWS_REGION: str = "ap-northeast-2"
    S3_BUCKET: str | None = None
    S3_ENDPOINT_URL: str | None = None
    # 공개 이미지를 서빙하는 CloudFront 도메인 (예: https://cdn.vivac.app)
    CDN_BASE_URL: str | None = None
    # presigned URL 만료 시간(초). 업로드/비공개 조회 공통.
    S3_PRESIGN_EXPIRE_SECONDS: int = 3600

    @field_validator("CORS_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    # -------------------------------------------------------------------------
    # Computed fields
    # -------------------------------------------------------------------------
    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @model_validator(mode="after")
    def _apply_cors_defaults(self) -> "Settings":
        if self.CORS_ALLOWED_ORIGINS is None:
            self.CORS_ALLOWED_ORIGINS = (
                ["http://localhost:3000", "http://127.0.0.1:3000"]
                if self.ENVIRONMENT == "local"
                else []
            )
        return self

    @model_validator(mode="after")
    def _validate_prod_requirements(self) -> "Settings":
        if self.ENVIRONMENT != "prod":
            return self

        errors: list[str] = []

        if self.DB_HOST in ("localhost", "127.0.0.1", ""):
            errors.append(
                f"DB_HOST={self.DB_HOST!r} is not allowed in prod "
                "(use the Lightsail managed DB endpoint)."
            )

        if "your_db_password_here" in self.DB_PASSWORD or "CHANGE_ME" in self.DB_PASSWORD:
            errors.append("DB_PASSWORD still contains a placeholder value.")

        if "your_google_client_id_here" in self.GOOGLE_CLIENT_ID:
            errors.append("GOOGLE_CLIENT_ID still contains a placeholder value.")

        if "CHANGE_ME" in self.JWT_SECRET_KEY:
            errors.append("JWT_SECRET_KEY still contains a placeholder value.")
        if len(self.JWT_SECRET_KEY) < 32:
            errors.append("JWT_SECRET_KEY must be at least 32 characters in prod.")

        if "CHANGE_ME" in self.ADMIN_SESSION_SECRET:
            errors.append("ADMIN_SESSION_SECRET still contains a placeholder value.")
        if len(self.ADMIN_SESSION_SECRET) < 32:
            errors.append(
                "ADMIN_SESSION_SECRET must be at least 32 characters in prod."
            )

        if not self.CORS_ALLOWED_ORIGINS:
            errors.append("CORS_ALLOWED_ORIGINS must be set in prod.")
        for origin in self.CORS_ALLOWED_ORIGINS or []:
            if origin == "*":
                errors.append("CORS_ALLOWED_ORIGINS cannot include '*' in prod.")
            elif "localhost" in origin or "127.0.0.1" in origin:
                errors.append(
                    f"CORS_ALLOWED_ORIGINS={origin!r} is not allowed in prod."
                )

        if errors:
            joined = "\n  - ".join(errors)
            raise ValueError(
                "Invalid prod configuration:\n  - " + joined
            )

        return self


settings = Settings()
