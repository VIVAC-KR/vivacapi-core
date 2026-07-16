from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from vivacapi.models.invite import InviteStatus
from vivacapi.models.spot_group import GroupRole


class InviteCreate(BaseModel):
    """group_uid/group_role은 둘 다 주거나 둘 다 비워야 한다(그룹 초대 vs
    일반 리퍼럴 링크)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"group_uid": "6dHkQ2mNpXyB4jRt8wLsA1", "group_role": "member"}
        }
    )

    group_uid: str | None = None
    group_role: GroupRole | None = None

    @model_validator(mode="after")
    def _check_group_fields_paired(self) -> "InviteCreate":
        if (self.group_uid is None) != (self.group_role is None):
            raise ValueError("group_uid and group_role must be provided together")
        return self


class InviteResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "uid": "7pQmN3vXyB4jRt8wLsA1cD",
                "group_uid": "6dHkQ2mNpXyB4jRt8wLsA1",
                "group_role": "member",
                "status": "pending",
                "created_at": "2026-07-16T09:00:00+09:00",
            }
        },
    )

    uid: str
    group_uid: str | None
    group_role: GroupRole | None
    status: InviteStatus
    created_at: datetime | None


class InvitePreview(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "inviter_nickname": "불멍러",
                "group_name": "종강 여행 스팟 모음",
                "status": "pending",
            }
        }
    )

    inviter_nickname: str
    group_name: str | None
    status: InviteStatus
