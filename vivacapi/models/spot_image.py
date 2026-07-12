from datetime import datetime
from enum import StrEnum

import shortuuid
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from vivacapi.core.database import Base


class SpotImageRole(StrEnum):
    THUMBNAIL = "thumbnail"  # 대표 이미지
    DETAIL = "detail"  # 상세 이미지


class SpotImage(Base):
    __tablename__ = "spot_images"
    __table_args__ = (
        CheckConstraint(
            "uid ~ '^[0-9A-Za-z]{22}$'", name="ck_spot_images_uid_format"
        ),
    )

    uid: Mapped[str] = mapped_column(
        String(22), primary_key=True, default=shortuuid.uuid
    )
    spot_uid: Mapped[str] = mapped_column(
        String(22), ForeignKey("spots.uid"), nullable=False, index=True
    )

    # S3 객체 키. CDN 도메인이 바뀌어도 DB를 건드리지 않도록 풀 URL이 아닌 key만 저장.
    s3_key: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[SpotImageRole] = mapped_column(
        Enum(
            SpotImageRole,
            name="spot_image_role",
            native_enum=True,
            create_type=False,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=SpotImageRole.DETAIL,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # 공개 이미지는 CDN URL로, 비공개는 presigned URL로 서빙한다.
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    content_type: Mapped[str | None] = mapped_column(String)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
