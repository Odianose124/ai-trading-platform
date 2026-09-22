from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.websocket.manager import websocket_manager


class MT5StreamService:
    """
    Publishes live MT5 websocket events.

    Data source:
    MT5 worker manager.

    No simulated prices.
    No hardcoded symbols.
    """

    def __init__(self):
        self.running = False
        self.task = None
        self.event_queue = asyncio.Queue()


    async def publish_snapshot(
        self,
        snapshot: dict,
    ):

        await self.event_queue.put(
            {
                "type": "mt5_snapshot",
                "timestamp": datetime.now(
                    timezone.utc
                ).isoformat(),
                **snapshot,
            }
        )


    async def publish_tick(
        self,
        tick: dict,
    ):

        await self.event_queue.put(
            {
                "type": "mt5_tick",
                "source": "MetaTrader 5",
                "timestamp": datetime.now(
                    timezone.utc
                ).isoformat(),
                "data": tick,
            }
        )


    async def start(self):

        self.running = True

        while self.running:

            event = await self.event_queue.get()

            await websocket_manager.broadcast(
                event
            )


    async def stop(self):

        self.running = False


mt5_stream_service = MT5StreamService()

