from fastapi import APIRouter, Depends
from app.api.v1.endpoints import auth, internal_jobs
from app.core.deps import require_staff

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_v1_router.include_router(internal_jobs.router, prefix="/internal/jobs",
    tags=["internal"],
    dependencies=[Depends(require_staff)],)
