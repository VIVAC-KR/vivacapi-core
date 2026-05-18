import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.errors import AppException, ErrorCode
from app.api.v1.routers import api_v1_router
from app.workers.job_worker import job_worker_loop, startup_orphan_cleanup

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
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(api_v1_router, prefix="/v1")
# app.include_router(auth_router)
# app.include_router(internal_jobs_router)


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
        details=exc.errors(),
    )


_STATUS_TO_CODE: dict[int, ErrorCode] = {
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.USER_NOT_FOUND,
    422: ErrorCode.VALIDATION_ERROR,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}


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
