from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.models.spot_image import SpotImage, SpotImageRole


async def list_images_by_spot(
    session: AsyncSession, spot_uid: str
) -> list[SpotImage]:
    query = (
        select(SpotImage)
        .where(SpotImage.spot_uid == spot_uid)
        .order_by(SpotImage.sort_order, SpotImage.created_at)
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def create_image(
    session: AsyncSession,
    *,
    spot_uid: str,
    s3_key: str,
    role: SpotImageRole,
    sort_order: int,
    is_public: bool,
    content_type: str | None,
) -> SpotImage:
    image = SpotImage(
        spot_uid=spot_uid,
        s3_key=s3_key,
        role=role,
        sort_order=sort_order,
        is_public=is_public,
        content_type=content_type,
    )
    session.add(image)
    await session.commit()
    await session.refresh(image)
    return image
