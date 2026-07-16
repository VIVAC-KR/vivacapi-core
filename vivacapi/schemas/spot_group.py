from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from vivacapi.models.spot_group import GroupRole, GroupVisibility


class SpotGroupCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "종강 여행 스팟 모음",
                "description": "다낭 여행 갈 때 참고할 스팟 모음",
                "visibility": "private",
            }
        }
    )

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    visibility: GroupVisibility = GroupVisibility.PRIVATE


class SpotGroupUpdate(BaseModel):
    """부분 수정. 전달된 필드만 반영(exclude_unset)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "종강 여행 스팟 모음 (수정)",
                "visibility": "invite_only",
            }
        }
    )

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    visibility: GroupVisibility | None = None


class SpotGroupListItem(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "uid": "Kx7mQ2pL9vNc4wZtR8bYaS",
                "name": "종강 여행 스팟 모음",
                "visibility": "private",
                "my_role": "owner",
                "spot_count": 12,
                "updated_at": "2026-07-10T12:00:00Z",
            }
        },
    )

    uid: str
    name: str
    visibility: GroupVisibility
    my_role: GroupRole
    spot_count: int
    updated_at: datetime | None


class SpotGroupDetail(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "uid": "Kx7mQ2pL9vNc4wZtR8bYaS",
                "name": "종강 여행 스팟 모음",
                "description": "다낭 여행 갈 때 참고할 스팟 모음",
                "visibility": "private",
                "spot_count": 12,
                "my_role": "owner",
                "created_at": "2026-06-01T09:00:00Z",
                "updated_at": "2026-07-10T12:00:00Z",
            }
        },
    )

    uid: str
    name: str
    description: str | None
    visibility: GroupVisibility
    spot_count: int
    my_role: GroupRole | None
    created_at: datetime | None
    updated_at: datetime | None


class SpotGroupMemberOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "user_uid": "Jd8NpQ3xTmC7vRk2YbW9aZ",
                "role": "editor",
                "created_at": "2026-06-05T10:30:00Z",
            }
        },
    )

    user_uid: str
    role: GroupRole
    created_at: datetime | None


class SpotGroupMemberInvite(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_uid": "Jd8NpQ3xTmC7vRk2YbW9aZ",
                "role": "editor",
            }
        }
    )

    user_uid: str
    role: GroupRole


class SpotGroupMemberRoleUpdate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"role": "editor"}})

    role: GroupRole


class SpotGroupSpotAdd(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"spot_uid": "Bq3FhT9xLpW2vNc8ZmYaR1"}}
    )

    spot_uid: str


class SpotGroupSpotItem(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "uid": "Bq3FhT9xLpW2vNc8ZmYaR1",
                "title": "연세대 근처 감성 카페",
                "trust_tier": 2,
                "thumbnail_url": "https://cdn.vivac.app/spots/Bq3FhT9xLpW2vNc8ZmYaR1/thumb.jpg",
                "region_short": "서울",
                "category": ["cafe"],
                "added_by_uid": "Jd8NpQ3xTmC7vRk2YbW9aZ",
                "added_at": "2026-07-08T15:20:00Z",
            }
        }
    )

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
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "uid": "Kx7mQ2pL9vNc4wZtR8bYaS",
                "name": "종강 여행 스팟 모음",
                "visibility": "private",
                "member_count": 3,
                "spot_count": 12,
                "created_at": "2026-06-01T09:00:00Z",
                "updated_at": "2026-07-10T12:00:00Z",
            }
        },
    )

    uid: str
    name: str
    visibility: GroupVisibility
    member_count: int
    spot_count: int
    created_at: datetime | None
    updated_at: datetime | None


class SpotGroupAdminDetail(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "uid": "Kx7mQ2pL9vNc4wZtR8bYaS",
                "name": "종강 여행 스팟 모음",
                "description": "다낭 여행 갈 때 참고할 스팟 모음",
                "visibility": "private",
                "member_count": 3,
                "spot_count": 12,
                "created_at": "2026-06-01T09:00:00Z",
                "updated_at": "2026-07-10T12:00:00Z",
            }
        },
    )

    uid: str
    name: str
    description: str | None
    visibility: GroupVisibility
    member_count: int
    spot_count: int
    created_at: datetime | None
    updated_at: datetime | None


class SpotGroupAdminMemberOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_uid": "Jd8NpQ3xTmC7vRk2YbW9aZ",
                "nickname": "여행가는캠퍼",
                "email": "camper@example.com",
                "role": "editor",
                "invited_by_uid": "Ht5rV8nDpG2sLwK4Ux6yQ3",
                "created_at": "2026-06-05T10:30:00Z",
            }
        }
    )

    user_uid: str
    nickname: str
    email: str
    role: GroupRole
    invited_by_uid: str | None
    created_at: datetime | None
