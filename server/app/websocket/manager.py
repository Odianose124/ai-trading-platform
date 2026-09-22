from __future__ import annotations

from asyncio import Lock
from fastapi import WebSocket


class WebSocketManager:
    """
    Manages connected frontend websocket clients.

    This layer only transports live data.
    It does not create MT5 connections.
    """

    def __init__(self):
        self.connections: list[WebSocket] = []
        self.lock = Lock()


    async def connect(
        self,
        websocket: WebSocket,
    ):
        await websocket.accept()

        async with self.lock:
            self.connections.append(websocket)


    async def disconnect(
        self,
        websocket: WebSocket,
    ):
        async with self.lock:
            if websocket in self.connections:
                self.connections.remove(websocket)


    async def broadcast(
        self,
        message: dict,
    ):
        async with self.lock:

            disconnected = []

            for websocket in self.connections:

                try:
                    await websocket.send_json(
                        message
                    )

                except Exception:
                    disconnected.append(
                        websocket
                    )


            for websocket in disconnected:

                if websocket in self.connections:
                    self.connections.remove(
                        websocket
                    )


websocket_manager = WebSocketManager()
