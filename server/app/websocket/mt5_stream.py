from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.websocket.manager import websocket_manager


class MT5StreamService:
    """
    Publishes live MT5 websocket events.

    Every event is associated with an authenticated user.

    No simulated prices.
    No hardcoded symbols.
    """

    def __init__(self):
        self.running = False
        self.event_queue = asyncio.Queue()

    async def publish_snapshot(
        self,
        user_id: int,
        snapshot: dict,
    ):
        await self.event_queue.put(
            {
                "user_id": user_id,
                "message": {
                    "type": "mt5_snapshot",
                    "timestamp": datetime.now(
                        timezone.utc
                    ).isoformat(),
                    **snapshot,
                },
            }
        )

    async def publish_tick(
        self,
        user_id: int,
        tick: dict,
    ):
        await self.event_queue.put(
            {
                "user_id": user_id,
                "message": {
                    "type": "mt5_tick",
                    "source": "MetaTrader 5",
                    "timestamp": datetime.now(
                        timezone.utc
                    ).isoformat(),
                    "data": tick,
                },
            }
        )

    async def start(self):
        self.running = True

        while self.running:
            event = await self.event_queue.get()

            if event is None:
                break

            user_id = event["user_id"]
            message = event["message"]

            await websocket_manager.send_to_user(
                user_id=user_id,
                message=message,
            )

    async def stop(self):
        self.running = False
        await self.event_queue.put(None)


mt5_stream_service = MT5StreamService()
