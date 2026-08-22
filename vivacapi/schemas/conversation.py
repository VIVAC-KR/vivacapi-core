from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from vivacapi.models.conversation import ConversationType


class ConversationCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "direct",
                "participant_uids": ["Jd8NpQ3xTmC7vRk2YbW9aZ"],
                "name": None,
            }
        }
    )

    type: ConversationType
    participant_uids: list[str] = Field(min_length=1)
    name: str | None = Field(None, max_length=100)


class ConversationListItem(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "uid": "Kx7mQ2pL9vNc4wZtR8bYaS",
                "type": "direct",
                "name": None,
                "last_message_preview": "내일 몇 시에 도착해?",
                "last_message_at": "2026-08-20T10:00:00Z",
                "unread_count": 2,
                "updated_at": "2026-08-20T10:00:00Z",
            }
        },
    )

    uid: str
    type: ConversationType
    name: str | None
    last_message_preview: str | None
    last_message_at: datetime | None
    unread_count: int
    updated_at: datetime


class ConversationDetail(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "uid": "Kx7mQ2pL9vNc4wZtR8bYaS",
                "type": "direct",
                "name": None,
                "participant_uids": [
                    "Jd8NpQ3xTmC7vRk2YbW9aZ",
                    "Ht5rV8nDpG2sLwK4Ux6yQ3",
                ],
                "created_at": "2026-08-01T09:00:00Z",
                "updated_at": "2026-08-20T10:00:00Z",
            }
        },
    )

    uid: str
    type: ConversationType
    name: str | None
    participant_uids: list[str]
    created_at: datetime
    updated_at: datetime
