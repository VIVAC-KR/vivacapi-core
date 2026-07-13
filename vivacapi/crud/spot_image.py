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


async def get_thumbnails_by_spots(
    session: AsyncSession, spot_uids: list[str]
) -> dict[str, SpotImage]:
    """spot_uid별 대표 이미지(THUMBNAIL) 1건. 목록 화면에서 N+1 없이 일괄 조회한다.

    한 spot에 THUMBNAIL이 여러 장이면 sort_order가 가장 앞선 것을 대표로 쓴다.
    """
    if not spot_uids:
        return {}
    query = (
        select(SpotImage)
        .where(
            SpotImage.spot_uid.in_(spot_uids),
            SpotImage.role == SpotImageRole.THUMBNAIL,
        )
        .order_by(SpotImage.spot_uid, SpotImage.sort_order, SpotImage.created_at)
    )
    result = await session.execute(query)
    thumbnails: dict[str, SpotImage] = {}
    for image in result.scalars().all():
        thumbnails.setdefault(image.spot_uid, image)
    return thumbnails


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
