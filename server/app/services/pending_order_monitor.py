from __future__ import annotations

import asyncio

from app.services.pending_order_reconciliation_service import (
    pending_order_reconciliation_service,
)


class PendingOrderMonitor:
    """
    Background reconciliation loop for platform-owned pending MT5 orders.
    """

    POLL_INTERVAL_SECONDS = 2.0

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False

    async def start_background(self) -> None:
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(
            self._run(),
            name="pending-order-reconciliation",
        )

    async def stop(self) -> None:
        self._running = False

        if self._task is None:
            return

        self._task.cancel()

        try:
            await self._task
        except asyncio.CancelledError:
            pass

        self._task = None

    async def _run(self) -> None:
        while self._running:
            try:
                await asyncio.to_thread(
                    pending_order_reconciliation_service.reconcile_all_pending
                )
            except Exception:
                # The next polling cycle will retry reconciliation.
                pass

            try:
                await asyncio.sleep(
                    self.POLL_INTERVAL_SECONDS
                )
            except asyncio.CancelledError:
                break


pending_order_monitor = PendingOrderMonitor()
