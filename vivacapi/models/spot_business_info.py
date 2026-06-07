from datetime import date, datetime

import shortuuid
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from vivacapi.core.database import Base


class SpotBusinessInfo(Base):
    __tablename__ = "spot_business_info"

    uid: Mapped[str] = mapped_column(
        String(22), primary_key=True, default=shortuuid.uuid
    )
    spot_uid: Mapped[str] = mapped_column(
        String(22), ForeignKey("spots.uid"), nullable=False, index=True
    )

    business_reg_no: Mapped[str | None] = mapped_column(String)
    tourism_business_reg_no: Mapped[str | None] = mapped_column(String)
    business_type: Mapped[str | None] = mapped_column(String)
    operation_type: Mapped[str | None] = mapped_column(String)
    operating_agency: Mapped[str | None] = mapped_column(String)
    operating_status: Mapped[str | None] = mapped_column(String, index=True)

    national_park_no: Mapped[int | None] = mapped_column(Integer)
    national_park_office_code: Mapped[str | None] = mapped_column(String)
    national_park_serial_no: Mapped[str | None] = mapped_column(String)
    national_park_category_code: Mapped[str | None] = mapped_column(String)

    licensed_at: Mapped[date | None] = mapped_column(Date)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
