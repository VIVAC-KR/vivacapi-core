from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from vivacapi.models.invite import InviteStatus
from vivacapi.models.spot_group import GroupRole


class InviteCreate(BaseModel):
    group_uid: str | None = None
    group_role: GroupRole | None = None

    @model_validator(mode="after")
    def _check_group_fields_paired(self) -> "InviteCreate":
        if (self.group_uid is None) != (self.group_role is None):
            raise ValueError("group_uid and group_role must be provided together")
        return self


class InviteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str
    group_uid: str | None
    group_role: GroupRole | None
    status: InviteStatus
    created_at: datetime | None


class InvitePreview(BaseModel):
    inviter_nickname: str
    group_name: str | None
    status: InviteStatus
