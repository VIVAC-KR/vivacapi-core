from pydantic import BaseModel, ConfigDict


class SpotCategoryOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label_ko: str


class SpotCategoryOptionCreate(BaseModel):
    code: str
    label_ko: str
