from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
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
    # 빌드 시점 커밋 SHA (Docker ARG로 주입). 로컬 실행 시 "dev" 폴백 —
    # __version__은 release 시점에만 bump되므로 커밋 단위 식별에 필요하다.
    GIT_SHA: str = "dev"

    LOG_LEVEL: str = "INFO"

    # SQL 쿼리 로그. job worker가 2초마다 폴링해 켜두면 실제 앱 로그가 묻힌다.
    # 기본 off, 쿼리를 볼 때만 켠다.
    DB_ECHO: bool = False

    # -------------------------------------------------------------------------
    # 데이터베이스
    # local: docker-compose / dev·prod: RDS 프라이빗 엔드포인트 (VPC 직접 접속)
    # -------------------------------------------------------------------------
    DB_HOST: str = "localhost"
    DB_PORT: str = "5432"
    DB_NAME: str
    DB_USER: str
    # SecretStr — repr/model_dump 시 '**********'로 마스킹돼 로그 유출을 막는다.
    DB_PASSWORD: SecretStr

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
    JWT_SECRET_KEY: SecretStr
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ADMIN_ACCESS_TOKEN_EXPIRE_HOURS: int = 8

    # -------------------------------------------------------------------------
    # SQLAdmin (/admin) 세션
    # SessionMiddleware의 서명/암호화 키. JWT_SECRET_KEY와 분리해
    # 어드민 세션 노출 시 토큰 발급키 유출까지 번지지 않도록 한다.
    # -------------------------------------------------------------------------
    ADMIN_SESSION_SECRET: SecretStr

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
    # 이미지 업로드 최대 크기(바이트). register 시점에 head_object로 확인해
    # 초과하면 거부 + 삭제한다(VAC-14). presigned PUT 자체는 크기를 강제 못함.
    IMAGE_MAX_BYTES: int = 10 * 1024 * 1024  # 10MB

    # -------------------------------------------------------------------------
    # Slack (scripts/send_spots_slack.py 정기 발송 배치 전용)
    # 미설정 시 스크립트가 발송을 건너뛴다.
    # -------------------------------------------------------------------------
    SLACK_WEBHOOK_URL: str | None = None

    # -------------------------------------------------------------------------
    # 캐시 (Redis) — 공개 탐색 API(/v1/explore/spots) 응답 캐싱 + 레이트 리밋 카운터
    # 미설정(None) 시 캐싱 없이 항상 DB로 응답하고, 레이트 리밋도 걸리지 않는다
    # (둘 다 fail-open — Redis 장애로 서비스가 멈추지 않는 쪽을 택했다).
    # TTL은 S3_PRESIGN_EXPIRE_SECONDS보다 짧아야 한다 — 캐시된 응답에 박힌
    # 비공개 이미지 presigned URL이 캐시 수명 중 만료되면 안 되기 때문.
    # -------------------------------------------------------------------------
    REDIS_URL: str | None = None
    SPOTS_LIST_CACHE_TTL_SECONDS: int = 30
    SPOT_DETAIL_CACHE_TTL_SECONDS: int = 120

    # 좌표 없는 spot을 explore 계열 전체(목록/검색/상세)에서 제외한다.
    # 기본 False — 현재 prod spot은 좌표가 전부 NULL이라 켜는 순간 탐색 결과가
    # 0건이 된다. 좌표 적재가 끝난 뒤 env로 켠다.
    # (/v1/explore/spots/map은 이 값과 무관하게 항상 좌표 보유만 반환한다 —
    #  좌표 없는 핀은 지도에서 의미가 없기 때문.)
    EXPLORE_REQUIRE_COORDINATES: bool = False

    # -------------------------------------------------------------------------
    # API 문서 (/docs, /redoc, /openapi.json, /scalar)
    # 기본 False — prod에서 internal 어드민 스키마 노출을 막는다.
    # -------------------------------------------------------------------------
    ENABLE_API_DOCS: bool = False

    @field_validator("CORS_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    # computed_field가 아닌 일반 property — model_dump/직렬화에
    # 비밀번호가 포함된 DSN이 딸려 나가지 않도록 한다.
    @property
    def database_url(self) -> str:
        ssl = "?ssl=require" if self.ENVIRONMENT == "prod" else ""
        return (
            f"postgresql+asyncpg://{self.DB_USER}:"
            f"{self.DB_PASSWORD.get_secret_value()}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}{ssl}"
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

        db_password = self.DB_PASSWORD.get_secret_value()
        if "your_db_password_here" in db_password or "CHANGE_ME" in db_password:
            errors.append("DB_PASSWORD still contains a placeholder value.")

        if "your_google_client_id_here" in self.GOOGLE_CLIENT_ID:
            errors.append("GOOGLE_CLIENT_ID still contains a placeholder value.")

        jwt_secret = self.JWT_SECRET_KEY.get_secret_value()
        if "CHANGE_ME" in jwt_secret:
            errors.append("JWT_SECRET_KEY still contains a placeholder value.")
        if len(jwt_secret) < 32:
            errors.append("JWT_SECRET_KEY must be at least 32 characters in prod.")

        admin_secret = self.ADMIN_SESSION_SECRET.get_secret_value()
        if "CHANGE_ME" in admin_secret:
            errors.append("ADMIN_SESSION_SECRET still contains a placeholder value.")
        if len(admin_secret) < 32:
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
            raise ValueError("Invalid prod configuration:\n  - " + joined)

        return self


settings = Settings()
