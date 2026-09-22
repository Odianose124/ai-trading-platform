from __future__ import annotations

from asyncio import sleep
from datetime import datetime, timezone

from app.websocket.manager import websocket_manager


class MT5StreamService:
    """
    Publishes real MT5 market updates.

    No hardcoded prices.
    No simulated ticks.
    """


    def __init__(self):
        self.running = False


    async def publish_tick(
        self,
        tick: dict,
    ):

        await websocket_manager.broadcast(
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

            # MT5 worker integration will feed this.
            # This loop remains idle until real
            # worker tick events are connected.

            await sleep(1)


    def stop(self):

        self.running = False



mt5_stream_service = MT5StreamService()
