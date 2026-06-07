from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spot import Spot
from app.models.spot_business_info import SpotBusinessInfo
from app.schemas.spot_business_info import (
    SpotBusinessInfoBulkRequest,
    SpotBusinessInfoBulkRow,
)

_MAX_REASON_LEN = 500


async def _build_external_id_mapping(
    db: AsyncSession, external_ids: list[str]
) -> dict[str, list[str]]:
    if not external_ids:
        return {}
    result = await db.execute(
        select(Spot.external_id, Spot.uid).where(Spot.external_id.in_(external_ids))
    )
    mapping: dict[str, list[str]] = defaultdict(list)
    for ext_id, uid in result.all():
        if ext_id is not None:
            mapping[ext_id].append(uid)
    return mapping


async def _upsert_business_info_row(
    db: AsyncSession, spot_uid: str, row: SpotBusinessInfoBulkRow
) -> None:
    fields = row.model_dump(exclude={"spot_external_id"}, exclude_none=True)

    existing = (
        await db.execute(
            select(SpotBusinessInfo).where(SpotBusinessInfo.spot_uid == spot_uid)
        )
    ).scalar_one_or_none()

    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
    else:
        db.add(SpotBusinessInfo(spot_uid=spot_uid, **fields))

    await db.flush()


async def spot_business_info_bulk_upsert_handler(
    db: AsyncSession, payload: dict[str, Any]
) -> dict[str, Any]:
    """행 단위로 spot_business_info를 upsert한다.

    spot_external_id로 spots.uid를 매핑해 확정한 뒤 spot_uid 기준으로 upsert한다.
    매핑 실패(미존재/모호) 행은 행별 사유와 함께 실패로 기록되며, 단 한 건이라도
    실패하면 outer SAVEPOINT를 롤백해 전체 변경을 무효화한다.
    """
    request = SpotBusinessInfoBulkRequest.model_validate(payload)

    external_ids = list({row.spot_external_id for row in request.rows})
    mapping = await _build_external_id_mapping(db, external_ids)

    errors: list[dict[str, Any]] = []
    succeeded = 0

    outer_sp = await db.begin_nested()
    for index, row in enumerate(request.rows):
        row_sp = await db.begin_nested()
        try:
            uids = mapping.get(row.spot_external_id, [])
            if not uids:
                raise ValueError(
                    f"spot_external_id {row.spot_external_id!r} not found"
                )
            if len(uids) > 1:
                raise ValueError(
                    f"spot_external_id {row.spot_external_id!r} is ambiguous"
                )
            await _upsert_business_info_row(db, uids[0], row)
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
