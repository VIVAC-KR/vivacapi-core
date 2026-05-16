import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.user import create_user, mark_onboarding_survey_completed
from app.models.user import MembershipTier


async def test_create_user_assigns_random_nickname(db_session: AsyncSession):
    user = await create_user(
        db_session,
        email="alice@example.com",
        google_sub="sub-alice",
        name="Alice Real Name",
    )

    assert user.nickname
    parts = user.nickname.split("-")
    assert len(parts) == 3
    assert parts[2].isdigit()
    assert user.nickname != "Alice Real Name"
    assert user.nickname != "alice"
    assert user.membership_tier == MembershipTier.FREE


async def test_create_user_retries_on_nickname_conflict(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    nicknames = iter(
        [
            "duplicate-name-1234",
            "duplicate-name-1234",
            "unique-name-5678",
        ]
    )
    monkeypatch.setattr(
        "app.crud.user.generate_nickname",
        lambda: next(nicknames),
    )

    user1 = await create_user(
        db_session,
        email="dup1@example.com",
        google_sub="sub-dup1",
    )
    user2 = await create_user(
        db_session,
        email="dup2@example.com",
        google_sub="sub-dup2",
    )

    assert user1.nickname == "duplicate-name-1234"
    assert user2.nickname == "unique-name-5678"


async def test_mark_onboarding_survey_completed_transitions_tier(
    db_session: AsyncSession,
):
    user = await create_user(
        db_session,
        email="onboard@example.com",
        google_sub="sub-onboard",
    )

    assert user.membership_tier == MembershipTier.FREE
    assert user.onboarding_survey_completed_at is None

    await mark_onboarding_survey_completed(db_session, user)

    assert user.membership_tier == MembershipTier.MEMBER
    assert user.onboarding_survey_completed_at is not None
