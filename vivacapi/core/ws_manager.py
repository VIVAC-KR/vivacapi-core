from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """user_uid -> 활성 WebSocket 연결 집합을 들고 있는 인메모리 매니저.

    ponytail: EC2 단일 인스턴스 전제다. 인스턴스가 여러 개로 늘어나면 이
    인메모리 매핑은 인스턴스별로만 유효해 다른 인스턴스에 붙은 참여자에게는
    못 보낸다 — 그때 Redis pub/sub로 교체한다.
    """

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, user_uid: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[user_uid].add(websocket)

    def disconnect(self, user_uid: str, websocket: WebSocket) -> None:
        self._connections[user_uid].discard(websocket)
        if not self._connections[user_uid]:
            del self._connections[user_uid]

    async def send_to_user(self, user_uid: str, payload: dict[str, Any]) -> None:
        for websocket in list(self._connections.get(user_uid, ())):
            try:
                await websocket.send_json(payload)
            except Exception:
                self.disconnect(user_uid, websocket)


manager = ConnectionManager()
