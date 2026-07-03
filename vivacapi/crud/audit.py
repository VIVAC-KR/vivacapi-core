from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.models.audit_log import AuditLog
from vivacapi.models.user import User
from vivacapi.schemas.audit import AuditLogEntry, FieldChange

# UPDATE마다 항상 바뀌어 diff에 노이즈만 되는 필드
_IGNORED_FIELDS = {"updated_at"}


async def set_audit_user(session: AsyncSession, user_uid: str) -> None:
    """이후 이 트랜잭션의 쓰기에 대해 audit_log.changed_by를 채운다.

    SET LOCAL이라 커밋/롤백 시 자동 해제된다. 쓰기 전에 호출할 것.
    """
    await session.execute(
        text("SELECT set_config('app.user_id', :uid, true)"), {"uid": user_uid}
    )


def _compute_changes(
    old: dict[str, Any] | None, new: dict[str, Any] | None
) -> dict[str, FieldChange]:
    old = old or {}
    new = new or {}
    keys = (old.keys() | new.keys()) - _IGNORED_FIELDS
    return {
        k: FieldChange(before=old.get(k), after=new.get(k))
        for k in keys
        if old.get(k) != new.get(k)
    }


async def get_history(
    session: AsyncSession,
    table_name: str,
    row_uid: str,
    limit: int = 100,
) -> list[AuditLogEntry]:
    rows = (
        await session.execute(
            select(AuditLog, User.name, User.nickname)
            .outerjoin(User, User.uid == AuditLog.changed_by)
            .where(AuditLog.table_name == table_name, AuditLog.row_uid == row_uid)
            # 같은 트랜잭션 내 변경은 changed_at(now()=트랜잭션 시각)이 동일하므로
            # id를 tiebreaker로 두어 순서를 결정적으로 만든다.
            .order_by(AuditLog.changed_at.desc(), AuditLog.id.desc())
            .limit(limit)
        )
    ).all()
    return [
        AuditLogEntry(
            changed_at=log.changed_at,
            action=log.action,
            changed_by=log.changed_by,
            changed_by_name=name or nickname,
            changes=_compute_changes(log.old_data, log.new_data),
        )
        for log, name, nickname in rows
    ]
