from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from jwt.exceptions import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.database import get_db
from vivacapi.core.security import decode_token
from vivacapi.core.ws_manager import manager
from vivacapi.crud.user import get_user_by_id

router = APIRouter()

_UNAUTHORIZED = 4401


@router.websocket("/conversations")
async def ws_conversations(
    websocket: WebSocket,
    token: str = Query(...),
    session: AsyncSession = Depends(get_db),
) -> None:
    """대화 메시지 실시간 push 채널. 브라우저 WebSocket은 커스텀 헤더를 못 실어
    Authorization 대신 쿼리 파라미터로 액세스 토큰을 받는다.

    클라이언트로부터의 프레임은 사용하지 않는다 — 전송은 REST
    `POST /v1/conversations/{uid}/messages`로만 하고, 이 연결은 온라인 참여자에게
    저장된 메시지를 push하는 단방향 채널이다.
    """
    try:
        payload = decode_token(token)
    except InvalidTokenError:
        await websocket.close(code=_UNAUTHORIZED)
        return
    if payload.get("type") != "access":
        await websocket.close(code=_UNAUTHORIZED)
        return

    user = await get_user_by_id(session, payload["sub"])
    if user is None or not user.is_active:
        await websocket.close(code=_UNAUTHORIZED)
        return

    await manager.connect(user.uid, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(user.uid, websocket)
