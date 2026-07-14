from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class SpotBusinessInfoBulkRow(BaseModel):
    spot_external_id: str

    business_reg_no: str | None = None
    tourism_business_reg_no: str | None = None
    business_type: str | None = None
    operation_type: str | None = None
    operating_agency: str | None = None
    operating_status: str | None = None

    national_park_no: int | None = None
    national_park_office_code: str | None = None
    national_park_serial_no: str | None = None
    national_park_category_code: str | None = None

    licensed_at: date | None = None


class SpotBusinessInfoBulkRequest(BaseModel):
    dry_run: bool = False
    rows: list[SpotBusinessInfoBulkRow] = Field(min_length=1, max_length=5000)


# ---------------------------------------------------------------------------
# Internal admin (vivac-console) — 단건 조회/수정
# ---------------------------------------------------------------------------


class SpotBusinessInfoAdminListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    spot_uid: str
    spot_title: str
    business_type: str | None
    operating_status: str | None
    updated_at: datetime | None


class SpotBusinessInfoAdminDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    spot_uid: str
    business_reg_no: str | None
    tourism_business_reg_no: str | None
    business_type: str | None
    operation_type: str | None
    operating_agency: str | None
    operating_status: str | None
    national_park_no: int | None
    national_park_office_code: str | None
    national_park_serial_no: str | None
    national_park_category_code: str | None
    licensed_at: date | None
    created_at: datetime | None
    updated_at: datetime | None


class SpotBusinessInfoUpdate(BaseModel):
    """부분 수정. 전달된 필드만 반영(exclude_unset). spot_uid 연결은 불변."""

    business_reg_no: str | None = None
    tourism_business_reg_no: str | None = None
    business_type: str | None = None
    operation_type: str | None = None
    operating_agency: str | None = None
    operating_status: str | None = None
    national_park_no: int | None = None
    national_park_office_code: str | None = None
    national_park_serial_no: str | None = None
    national_park_category_code: str | None = None
    licensed_at: date | None = None
