from __future__ import annotations

from asyncio import Lock
from fastapi import WebSocket


class WebSocketManager:
    """
    Manages authenticated frontend websocket clients.

    Connections are isolated by authenticated user_id.

    Each websocket can maintain its own requested MT5 symbols.
    The manager exposes the union of symbols requested by all
    connections belonging to the same authenticated user.
    """

    def __init__(self):
        self.connections: dict[int, set[WebSocket]] = {}
        self.subscriptions: dict[
            int,
            dict[WebSocket, set[str]],
        ] = {}
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

            user_subscriptions = self.subscriptions.setdefault(
                user_id,
                {},
            )

            user_subscriptions[websocket] = set()

    async def disconnect(
        self,
        websocket: WebSocket,
        user_id: int,
    ) -> set[str]:
        async with self.lock:
            user_connections = self.connections.get(user_id)

            if user_connections is not None:
                user_connections.discard(websocket)

                if not user_connections:
                    self.connections.pop(
                        user_id,
                        None,
                    )

            user_subscriptions = self.subscriptions.get(
                user_id
            )

            if user_subscriptions is not None:
                user_subscriptions.pop(
                    websocket,
                    None,
                )

                if not user_subscriptions:
                    self.subscriptions.pop(
                        user_id,
                        None,
                    )

            return self._subscription_union_locked(
                user_id
            )

    async def set_subscription(
        self,
        websocket: WebSocket,
        user_id: int,
        symbols: list[str],
    ) -> set[str]:
        normalized: set[str] = set()

        for symbol in symbols:
            if isinstance(symbol, str):
                value = symbol.strip().upper()

                if value:
                    normalized.add(value)

        async with self.lock:
            user_subscriptions = self.subscriptions.get(
                user_id
            )

            if user_subscriptions is None:
                return set()

            if websocket not in user_subscriptions:
                return set()

            user_subscriptions[websocket] = normalized

            return self._subscription_union_locked(
                user_id
            )

    def _subscription_union_locked(
        self,
        user_id: int,
    ) -> set[str]:
        user_subscriptions = self.subscriptions.get(
            user_id
        )

        if not user_subscriptions:
            return set()

        result: set[str] = set()

        for symbols in user_subscriptions.values():
            result.update(symbols)

        return result

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

                user_subscriptions = self.subscriptions.get(
                    user_id
                )

                if user_subscriptions is not None:
                    user_subscriptions.pop(
                        websocket,
                        None,
                    )

            if not user_connections:
                self.connections.pop(
                    user_id,
                    None,
                )

                self.subscriptions.pop(
                    user_id,
                    None,
                )


websocket_manager = WebSocketManager()
