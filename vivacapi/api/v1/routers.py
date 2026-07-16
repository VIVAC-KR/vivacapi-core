from fastapi import APIRouter, Depends
from vivacapi.api.v1.endpoints import (
    admin_auth,
    auth,
    explore,
    internal_jobs,
    internal_spot_business_info,
    internal_spot_groups,
    internal_spot_images,
    internal_spot_options,
    internal_spots,
    invites,
    spot_groups,
)
from vivacapi.core.deps import require_staff

api_v1_router = APIRouter()
api_v1_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_v1_router.include_router(explore.router, prefix="/explore", tags=["explore"])
api_v1_router.include_router(spot_groups.router, prefix="/groups", tags=["spot-groups"])
api_v1_router.include_router(invites.router, prefix="/invites", tags=["invites"])
api_v1_router.include_router(
    admin_auth.router, prefix="/admin/auth", tags=["admin-auth"]
)
api_v1_router.include_router(
    internal_jobs.router,
    prefix="/internal/jobs",
    tags=["internal"],
    dependencies=[Depends(require_staff)],
)
api_v1_router.include_router(
    internal_spots.router,
    prefix="/internal/spots",
    tags=["internal"],
    dependencies=[Depends(require_staff)],
)
api_v1_router.include_router(
    internal_spot_images.router,
    prefix="/internal/spots",
    tags=["internal"],
    dependencies=[Depends(require_staff)],
)
api_v1_router.include_router(
    internal_spot_business_info.router,
    prefix="/internal/spot-business-info",
    tags=["internal"],
    dependencies=[Depends(require_staff)],
)
api_v1_router.include_router(
    internal_spot_options.router,
    prefix="/internal/spot-options",
    tags=["internal"],
    dependencies=[Depends(require_staff)],
)
api_v1_router.include_router(
    internal_spot_groups.router,
    prefix="/internal/groups",
    tags=["internal"],
    dependencies=[Depends(require_staff)],
)
