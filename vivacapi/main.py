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
from vivacapi.core.config import settings
from vivacapi.core.database import engine
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.api.v1.routers import api_v1_router
from vivacapi.models.user import User
from vivacapi.workers.job_worker import job_worker_loop, startup_orphan_cleanup

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


app = FastAPI(
    title="VIVAC API",
    description="캠퍼를 위한 장소 큐레이션 서비스",
    version=__version__,
    lifespan=lifespan,
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
        secret_key=settings.ADMIN_SESSION_SECRET.get_secret_value()
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
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.exception(
        "Unhandled exception on %s %s", request.method, request.url.path
    )
    return _error_response(
        status_code=500,
        code=ErrorCode.INTERNAL_ERROR.value,
        message="Internal server error",
    )


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "environment": settings.ENVIRONMENT}


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
