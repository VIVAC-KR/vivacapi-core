import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from scalar_fastapi import get_scalar_api_reference
from sqladmin import Admin, ModelView
from starlette.exceptions import HTTPException

from vivacapi import __version__
from vivacapi.admin.auth import AdminAuth
from vivacapi.core import cache
from vivacapi.core.config import settings
from vivacapi.core.database import engine
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.api.v1.routers import api_v1_router
from vivacapi.models.user import User
from vivacapi.workers.job_worker import job_worker_loop, startup_orphan_cleanup

# uvicorn은 uvicorn.* logger만 설정하고 root는 건드리지 않는다 → vivacapi.*
# 로그가 handler 없는 root를 거쳐 lastResort(WARNING)로 떨어지고 INFO가 통째로
# 유실된다. root에 handler를 달아 앱 로그를 stderr(→ awslogs)로 흘린다.
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    orphan_count = await startup_orphan_cleanup()
    if orphan_count > 0:
        logger.warning("Cleaned up %d orphaned job(s) on startup", orphan_count)

    worker_task = asyncio.create_task(job_worker_loop())

    try:
        yield
    finally:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        await cache.close()


app = FastAPI(
    title="VIVAC API",
    description="캠퍼를 위한 장소 큐레이션 서비스",
    version=__version__,
    lifespan=lifespan,
    # ENABLE_API_DOCS=False(기본)면 internal 어드민 엔드포인트 스키마가 인증
    # 없이 노출되지 않도록 문서 라우트를 통째로 끈다. openapi_url이 None이면
    # /scalar도 함께 죽는다.
    docs_url="/docs" if settings.ENABLE_API_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_API_DOCS else None,
    openapi_tags=[
        {"name": "auth", "description": "앱 사용자 로그인/토큰 발급"},
        {"name": "explore", "description": "spot 탐색 (목록/지도/상세, 비로그인 가능)"},
        {"name": "spot-reviews", "description": "spot 리뷰 작성/조회/수정/삭제/신고"},
        {
            "name": "spot-groups",
            "description": "spot을 묶는 그룹과 멤버 관리 (앱 사용자용)",
        },
        {"name": "invites", "description": "그룹/앱 초대 링크 발급 및 수락"},
        {"name": "conversations", "description": "유저간 DM (1:1/그룹 대화, 메시지)"},
        {"name": "user-blocks", "description": "유저 차단/차단 해제"},
        {"name": "ws", "description": "대화 메시지 실시간 push용 WebSocket"},
        {"name": "admin-auth", "description": "vivac-console staff 로그인"},
        {"name": "internal-jobs", "description": "비동기 작업(job) 상태 조회"},
        {
            "name": "internal-db-dumps",
            "description": "DB 전체 덤프 작업 큐잉/다운로드 (SUPERUSER 전용)",
        },
        {
            "name": "internal-spots",
            "description": "vivac-console용 spot 조회/수정/할당 관리",
        },
        {
            "name": "internal-spot-images",
            "description": "spot 이미지 업로드(presign)/등록",
        },
        {
            "name": "internal-spot-business-info",
            "description": "spot 사업자정보 조회/수정",
        },
        {
            "name": "internal-spot-options",
            "description": "spot 필드 옵션값(카테고리 등) 관리",
        },
        {"name": "internal-spot-groups", "description": "spot 그룹 관리 (어드민 전용)"},
        {
            "name": "internal-review-reports",
            "description": "리뷰 신고 목록 조회 (모더레이션)",
        },
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Total-Count"],
)

app.include_router(api_v1_router, prefix="/v1")


admin = Admin(
    app,
    engine,
    authentication_backend=AdminAuth(
        secret_key=settings.ADMIN_SESSION_SECRET.get_secret_value(),
        # sqladmin은 넘긴 kwargs를 SessionMiddleware에 그대로 전달한다.
        # 기본값(https_only=False, max_age=14일)이면 staff 세션 쿠키에 Secure가
        # 없고 2주간 유효해, 어드민 JWT(8시간)보다 훨씬 무른 경로가 열린다.
        # same_site는 기본 "lax" 유지 — SQLAdmin에 CSRF 토큰이 없어 cross-site
        # POST를 막아주는 유일한 방어선이다.
        https_only=settings.ENVIRONMENT != "local",
        max_age=settings.JWT_ADMIN_ACCESS_TOKEN_EXPIRE_HOURS * 3600,
    ),
    templates_dir=str(Path(__file__).parent / "admin" / "templates"),
)
admin.templates.env.globals["google_client_id"] = settings.GOOGLE_CLIENT_ID


class UserAdmin(ModelView, model=User):
    column_list = [User.uid, User.email, User.nickname, User.is_staff]
    # 사용자 생성/삭제는 Google 로그인 흐름의 몫 — /admin에서는
    # 계정 상태/권한 토글만 허용해 조작 표면을 최소화한다.
    can_create = False
    can_delete = False
    form_columns = [User.is_active, User.is_staff]


admin.add_view(UserAdmin)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: object | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
            }
        },
    )


@app.exception_handler(AppException)
async def app_exception_handler(_request: Request, exc: AppException) -> JSONResponse:
    return _error_response(exc.status_code, exc.code.value, exc.message, exc.details)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return _error_response(
        status_code=422,
        code=ErrorCode.VALIDATION_ERROR.value,
        message="Invalid request",
        # ctx에 예외 객체가 담길 수 있어(커스텀 validator의 ValueError)
        # 그대로 직렬화하면 500이 난다 → jsonable_encoder로 변환.
        details=jsonable_encoder(exc.errors()),
    )


_STATUS_TO_CODE: dict[int, ErrorCode] = {
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    422: ErrorCode.VALIDATION_ERROR,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}


# starlette의 HTTPException에 등록해야 라우팅 404(존재하지 않는 경로)까지
# 표준 에러 봉투로 감싸진다. fastapi.HTTPException은 그 서브클래스라 함께 잡힌다.
@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    return _error_response(exc.status_code, code.value, str(exc.detail))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # ponytail: 요청 상관관계는 method/path/timestamp로 충분한 규모.
    # 동시 요청 구분이 실제로 막히면 X-Request-ID contextvar + logging.Filter 추가.
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return _error_response(
        status_code=500,
        code=ErrorCode.INTERNAL_ERROR.value,
        message="Internal server error",
    )


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT,
        "version": __version__,
    }


@app.get("/scalar", include_in_schema=False)
async def scalar_docs():
    reference = get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )
    badge = (
        '<div style="position:fixed;bottom:8px;left:8px;z-index:9999;'
        "font:11px monospace;background:#111;color:#0f0;"
        'padding:4px 8px;border-radius:4px;opacity:0.85;">'
        f"v{__version__} ({settings.GIT_SHA[:7]})</div>"
    )
    html = reference.body.decode().replace("</body>", badge + "</body>")
    return HTMLResponse(html)
