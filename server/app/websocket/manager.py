from __future__ import annotations

from asyncio import Lock
from fastapi import WebSocket


class WebSocketManager:
    """
    Manages connected frontend websocket clients.

    Connections are isolated by authenticated user_id.

    This layer only transports live data.
    It does not create MT5 connections.
    """

    def __init__(self):
        self.connections: dict[int, set[WebSocket]] = {}
        self.lock = Lock()

    async def connect(
        self,
        websocket: WebSocket,
        user_id: int,
    ):
        await websocket.accept()

        async with self.lock:
            user_connections = self.connections.setdefault(
                user_id,
                set(),
            )
            user_connections.add(websocket)

    async def disconnect(
        self,
        websocket: WebSocket,
        user_id: int,
    ):
        async with self.lock:
            user_connections = self.connections.get(user_id)

            if user_connections is None:
                return

            user_connections.discard(websocket)

            if not user_connections:
                self.connections.pop(
                    user_id,
                    None,
                )

    async def send_to_user(
        self,
        user_id: int,
        message: dict,
    ):
        async with self.lock:
            user_connections = self.connections.get(user_id)

            if not user_connections:
                return

            disconnected: list[WebSocket] = []

            for websocket in list(user_connections):
                try:
                    await websocket.send_json(message)

                except Exception:
                    disconnected.append(websocket)

            for websocket in disconnected:
                user_connections.discard(websocket)

            if not user_connections:
                self.connections.pop(
                    user_id,
                    None,
                )


websocket_manager = WebSocketManager()
