from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MessageCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"content": "내일 몇 시에 도착해?"}}
    )

    content: str = Field(min_length=1, max_length=4000)


class MessageOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "uid": "Bq3FhT9xLpW2vNc8ZmYaR1",
                "conversation_uid": "Kx7mQ2pL9vNc4wZtR8bYaS",
                "sender_uid": "Jd8NpQ3xTmC7vRk2YbW9aZ",
                "content": "내일 몇 시에 도착해?",
                "created_at": "2026-08-20T10:00:00Z",
            }
        },
    )

    uid: str
    conversation_uid: str
    sender_uid: str
    content: str
    created_at: datetime


class MessageListResponse(BaseModel):
    items: list[MessageOut]
    next_cursor: str | None
    has_more: bool
