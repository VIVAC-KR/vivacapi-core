from pydantic import BaseModel, ConfigDict

from vivacapi.models.spot_field_option import SpotOptionField


class SpotFieldOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field: SpotOptionField
    code: str
    label_ko: str


class SpotFieldOptionCreate(BaseModel):
    field: SpotOptionField
    code: str
    label_ko: str
