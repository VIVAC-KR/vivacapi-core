from datetime import date

from pydantic import BaseModel, Field


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
