from pydantic import BaseModel, ConfigDict


class SpotListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    title: str


class SpotDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    title: str
    address: str | None
    website_url: str | None


class SpotListResponse(BaseModel):
    items: list[SpotListItem]
    page: int
    total_pages: int
    total: int
