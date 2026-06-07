import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqladmin.authentication import AuthenticationBackend
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from vivacapi.core.config import settings
from vivacapi.core.database import AsyncSessionLocal
from vivacapi.core.security import verify_google_id_token
from vivacapi.crud.user import get_user_by_email, get_user_by_id

logger = logging.getLogger(__name__)

SESSION_USER_UID_KEY = "admin_user_uid"
SESSION_USER_EMAIL_KEY = "admin_user_email"


@asynccontextmanager
async def admin_db_session() -> AsyncIterator[AsyncSession]:
    """AdminAuth가 사용하는 DB 세션 컨텍스트.

    SQLAdmin은 FastAPI 의존성 주입 밖에서 동작하므로 라우터의 `get_db`
    오버라이드를 그대로 쓸 수 없다. 테스트에서는 monkeypatch로 이 함수를
    교체해 트랜잭션 격리된 세션을 주입한다.
    """
    async with AsyncSessionLocal() as session:
        yield session


class AdminAuth(AuthenticationBackend):
    """`/admin` 게이팅을 담당하는 SQLAdmin 인증 백엔드.

    로그인 폼은 Google Identity Services로 받은 `id_token`을 POST한다.
    Google JWT 검증 → 이메일 도메인 화이트리스트 → DB의 `is_staff=True`
    확인까지 통과해야 세션을 발급한다. `authenticate`는 매 요청마다
    세션의 user_uid로 DB를 다시 조회해 staff 권한이 살아있는지 확인한다.
    """

    async def login(self, request: Request) -> bool:
        form = await request.form()
        id_token = form.get("id_token")
        if not id_token:
            return False

        try:
            info = verify_google_id_token(str(id_token))
        except ValueError:
            logger.info("Admin login: invalid Google ID token")
            return False
        except Exception:
            logger.exception("Admin login: Google ID token verification failed")
            return False

        email = info.get("email")
        if not email:
            return False

        if settings.ALLOWED_EMAIL_DOMAIN:
            _, _, domain = email.partition("@")
            if domain.lower() != settings.ALLOWED_EMAIL_DOMAIN.lower():
                logger.info("Admin login: email domain not allowed: %s", email)
                return False

        async with admin_db_session() as db:
            user = await get_user_by_email(db, email)
            if user is None or not user.is_active or not user.is_staff:
                logger.info("Admin login: not a staff user: %s", email)
                return False

            request.session[SESSION_USER_UID_KEY] = user.uid
            request.session[SESSION_USER_EMAIL_KEY] = user.email

        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        user_uid = request.session.get(SESSION_USER_UID_KEY)
        if not user_uid:
            return False

        async with admin_db_session() as db:
            user = await get_user_by_id(db, user_uid)
            if user is None or not user.is_active or not user.is_staff:
                request.session.clear()
                return False

        return True
