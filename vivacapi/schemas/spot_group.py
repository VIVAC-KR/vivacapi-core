from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from vivacapi.models.spot_group import GroupRole, GroupVisibility


class SpotGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    visibility: GroupVisibility = GroupVisibility.PRIVATE


class SpotGroupUpdate(BaseModel):
    """부분 수정. 전달된 필드만 반영(exclude_unset)."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    visibility: GroupVisibility | None = None


class SpotGroupListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    name: str
    visibility: GroupVisibility
    my_role: GroupRole
    spot_count: int
    updated_at: datetime | None


class SpotGroupDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    name: str
    description: str | None
    visibility: GroupVisibility
    spot_count: int
    my_role: GroupRole | None
    created_at: datetime | None
    updated_at: datetime | None


class SpotGroupMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_uid: str
    role: GroupRole
    created_at: datetime | None


class SpotGroupMemberInvite(BaseModel):
    user_uid: str
    role: GroupRole


class SpotGroupMemberRoleUpdate(BaseModel):
    role: GroupRole


class SpotGroupSpotAdd(BaseModel):
    spot_uid: str


class SpotGroupSpotItem(BaseModel):
    uid: str
    title: str
    trust_tier: int | None
    thumbnail_url: str | None
    region_short: str | None
    category: list[str] | None
    added_by_uid: str
    added_at: datetime | None


# ---------------------------------------------------------------------------
# Internal admin (vivac-console) — 멤버십 무관 조회/모더레이션
# ---------------------------------------------------------------------------


class SpotGroupAdminListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    name: str
    visibility: GroupVisibility
    member_count: int
    spot_count: int
    created_at: datetime | None
    updated_at: datetime | None


class SpotGroupAdminDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    name: str
    description: str | None
    visibility: GroupVisibility
    member_count: int
    spot_count: int
    created_at: datetime | None
    updated_at: datetime | None


class SpotGroupAdminMemberOut(BaseModel):
    user_uid: str
    nickname: str
    email: str
    role: GroupRole
    invited_by_uid: str | None
    created_at: datetime | None
