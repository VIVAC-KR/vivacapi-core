from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.models.audit_log import AuditLog
from vivacapi.models.user import User
from vivacapi.schemas.audit import AuditLogEntry, FieldChange

# UPDATE마다 항상 바뀌어 diff에 노이즈만 되는 필드
_IGNORED_FIELDS = {"updated_at"}


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
            .order_by(AuditLog.changed_at.desc())
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
