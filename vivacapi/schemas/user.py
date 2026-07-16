from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field

from vivacapi.models.user import MembershipTier


class UserResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "uid": "j3kD9fQxT2mZ8pR1yN6vXa",
                "email": "camper1@gmail.com",
                "nickname": "happy-tiger-1234",
                "name": "김민준",
                "picture": "https://lh3.googleusercontent.com/a/AATXAJw...",
                "is_active": True,
                "membership_tier": "free",
                "identity_verified_at": None,
                "onboarding_survey_completed_at": "2026-06-01T09:00:00Z",
                "created_at": "2026-05-20T10:12:00Z",
                "updated_at": "2026-06-01T09:00:00Z",
                "is_identity_verified": False,
                "has_completed_onboarding_survey": True,
            }
        },
    )

    uid: str
    email: str
    nickname: str
    name: str | None
    picture: str | None
    is_active: bool
    membership_tier: MembershipTier
    identity_verified_at: datetime | None
    onboarding_survey_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_identity_verified(self) -> bool:
        return self.identity_verified_at is not None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_completed_onboarding_survey(self) -> bool:
        return self.onboarding_survey_completed_at is not None
