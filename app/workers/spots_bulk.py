from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spot import Spot
from app.schemas.spot import SpotBulkRequest, SpotBulkRow

_MAX_REASON_LEN = 500
_CONFLICT_COLS = ("source", "external_id")


async def _upsert_spot_row(db: AsyncSession, row: SpotBulkRow) -> None:
    values = row.model_dump(exclude_none=True)
    stmt = insert(Spot).values(**values)

    if row.source is not None and row.external_id is not None:
        update_cols = {
            col: stmt.excluded[col] for col in values if col not in _CONFLICT_COLS
        }
        if update_cols:
            stmt = stmt.on_conflict_do_update(
                index_elements=list(_CONFLICT_COLS), set_=update_cols
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=list(_CONFLICT_COLS))

    await db.execute(stmt)


async def spots_bulk_upsert_handler(
    db: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """행 단위로 spots를 upsert한다.

    모든 행 쓰기는 outer SAVEPOINT 안에서 실행되어, 실패 시 outer 트랜잭션
    (job.status/result 기록용)은 건드리지 않고 행 쓰기만 롤백할 수 있다.
    """
    request = SpotBulkRequest.model_validate(payload)

    errors: list[dict[str, Any]] = []
    succeeded = 0

    outer_sp = await db.begin_nested()
    for index, row in enumerate(request.rows):
        row_sp = await db.begin_nested()
        try:
            await _upsert_spot_row(db, row)
        except Exception as exc:
            await row_sp.rollback()
            reason = str(exc)
            if len(reason) > _MAX_REASON_LEN:
                reason = reason[:_MAX_REASON_LEN] + "..."
            errors.append({"index": index, "reason": reason})
        else:
            await row_sp.commit()
            succeeded += 1

    rolled_back = bool(errors) or request.dry_run
    if rolled_back:
        await outer_sp.rollback()
        if errors:
            succeeded = 0
    else:
        await outer_sp.commit()

    return {
        "succeeded": succeeded,
        "failed": len(errors),
        "dry_run": request.dry_run,
        "errors": errors,
    }
