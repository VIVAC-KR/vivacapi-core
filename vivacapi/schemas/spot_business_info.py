from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class SpotBusinessInfoBulkRow(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "spot_external_id": "camp-jiri-001",
                "business_reg_no": "123-45-67890",
                "tourism_business_reg_no": "제2023-000123호",
                "business_type": "야영장업",
                "operation_type": "직영",
                "operating_agency": "국립공원공단",
                "operating_status": "운영중",
                "national_park_no": 7,
                "national_park_office_code": "JIRI",
                "national_park_serial_no": "A-102",
                "national_park_category_code": "GENERAL_CAMP",
                "licensed_at": "2019-05-20",
            }
        }
    )

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
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "dry_run": False,
                "rows": [
                    {
                        "spot_external_id": "camp-jiri-001",
                        "business_type": "야영장업",
                        "operating_status": "운영중",
                    }
                ],
            }
        }
    )

    dry_run: bool = False
    rows: list[SpotBusinessInfoBulkRow] = Field(min_length=1, max_length=5000)


# ---------------------------------------------------------------------------
# Internal admin (vivac-console) — 단건 조회/수정
# ---------------------------------------------------------------------------


class SpotBusinessInfoAdminListItem(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "uid": "biz8fK3mQdX2pLrN7vTsZa",
                "spot_uid": "spotAB12cD34eF56gH78iJ",
                "spot_title": "지리산 뱀사골 야영장",
                "business_type": "야영장업",
                "operating_status": "운영중",
                "updated_at": "2026-05-10T09:00:00+09:00",
            }
        },
    )

    uid: str
    spot_uid: str
    spot_title: str
    business_type: str | None
    operating_status: str | None
    updated_at: datetime | None


class SpotBusinessInfoAdminDetail(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "uid": "biz8fK3mQdX2pLrN7vTsZa",
                "spot_uid": "spotAB12cD34eF56gH78iJ",
                "business_reg_no": "123-45-67890",
                "tourism_business_reg_no": "제2023-000123호",
                "business_type": "야영장업",
                "operation_type": "직영",
                "operating_agency": "국립공원공단",
                "operating_status": "운영중",
                "national_park_no": 7,
                "national_park_office_code": "JIRI",
                "national_park_serial_no": "A-102",
                "national_park_category_code": "GENERAL_CAMP",
                "licensed_at": "2019-05-20",
                "created_at": "2024-11-01T10:00:00+09:00",
                "updated_at": "2026-05-10T09:00:00+09:00",
            }
        },
    )

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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "operating_status": "휴업",
                "operating_agency": "OO군청",
            }
        }
    )

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
