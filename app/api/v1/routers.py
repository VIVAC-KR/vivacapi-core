from fastapi import APIRouter, Depends
from app.api.v1.endpoints import auth, explore, internal_jobs
from app.core.deps import require_staff

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_v1_router.include_router(explore.router, prefix="/explore", tags=["explore"])
api_v1_router.include_router(internal_jobs.router, prefix="/internal/jobs",
    tags=["internal"],
    dependencies=[Depends(require_staff)],)
