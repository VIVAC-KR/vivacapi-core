from pydantic import BaseModel, ConfigDict

from vivacapi.models.spot_field_option import SpotOptionField


class SpotFieldOption(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {"field": "category", "code": "CAFE", "label_ko": "카페"}
        },
    )

    field: SpotOptionField
    code: str
    label_ko: str


class SpotFieldOptionCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"field": "category", "code": "CAFE", "label_ko": "카페"}
        }
    )

    field: SpotOptionField
    code: str
    label_ko: str
