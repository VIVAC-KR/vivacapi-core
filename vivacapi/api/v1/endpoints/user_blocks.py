from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.api.v1.endpoints.summaries import BLOCK_USER_SUMMARY, UNBLOCK_USER_SUMMARY
from vivacapi.core.database import get_db
from vivacapi.core.deps import get_current_user
from vivacapi.core.errors import AppException, ErrorCode
from vivacapi.crud import user as crud_user
from vivacapi.crud import user_block as crud_block
from vivacapi.models.user import User

router = APIRouter()


@router.post(
    "/{user_uid}/block",
    status_code=status.HTTP_204_NO_CONTENT,
    summary=BLOCK_USER_SUMMARY,
)
async def block_user(
    user_uid: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """이미 차단한 상대를 다시 차단해도 에러 없이 그대로 유지된다(멱등). 차단하면
    상대와의 신규 DIRECT 대화 생성과 기존 DIRECT 대화의 메시지 전송이 막힌다."""
    if user_uid == user.uid:
        raise AppException(ErrorCode.VALIDATION_ERROR, "자기 자신은 차단할 수 없습니다")
    if await crud_user.get_user_by_id(session, user_uid) is None:
        raise AppException(ErrorCode.USER_NOT_FOUND, "User not found")
    await crud_block.block_user(session, blocker_uid=user.uid, blocked_uid=user_uid)


@router.delete(
    "/{user_uid}/block",
    status_code=status.HTTP_204_NO_CONTENT,
    summary=UNBLOCK_USER_SUMMARY,
)
async def unblock_user(
    user_uid: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """차단하지 않은 상대를 해제해도 에러 없이 그대로 통과한다(멱등)."""
    await crud_block.unblock_user(session, blocker_uid=user.uid, blocked_uid=user_uid)
