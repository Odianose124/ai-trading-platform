from typing import Any

import MetaTrader5 as mt5

from app.mt5.connection import (
    MT5ConnectionError,
    mt5_connection,
)


class PositionManager:
    """
    Read-only MT5 position manager.

    This class is currently responsible for:
    - reading live positions
    - filtering platform-owned positions
    - producing position summaries

    Live SL/TP modification and position closing will be moved into
    the controlled execution/management pipeline later.

    No method in this class initializes MT5 independently.
    No method in this class sends an MT5 order.
    """

    MAGIC_NUMBER = 202609

    def __init__(self) -> None:
        self.magic_number = self.MAGIC_NUMBER

    # ------------------------------------------------------------------
    # CONNECTION
    # ------------------------------------------------------------------

    def ensure_connection(self) -> bool:
        """
        Use the authoritative MT5 connection.

        Never call mt5.initialize() directly here.
        """

        try:
            mt5_connection.ensure_connected()
            return True

        except MT5ConnectionError:
            return False

    # ------------------------------------------------------------------
    # GET POSITIONS
    # ------------------------------------------------------------------

    def get_positions(
        self,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:

        if not self.ensure_connection():
            return []

        positions = mt5.positions_get()

        if positions is None:
            return []

        normalized_symbol = (
            symbol.strip().upper()
            if symbol
            else None
        )

        result: list[dict[str, Any]] = []

        for position in positions:

            if position.magic != self.magic_number:
                continue

            if (
                normalized_symbol
                and position.symbol.upper()
                != normalized_symbol
            ):
                continue

            if position.type == mt5.POSITION_TYPE_BUY:
                position_type = "buy"

            elif position.type == mt5.POSITION_TYPE_SELL:
                position_type = "sell"

            else:
                continue

            result.append(
                {
                    "ticket": position.ticket,
                    "symbol": position.symbol,
                    "type": position_type,
                    "volume": position.volume,
                    "entry_price": position.price_open,
                    "current_price": position.price_current,
                    "stop_loss": position.sl,
                    "take_profit": position.tp,
                    "profit": position.profit,
                    "swap": position.swap,
                    "magic": position.magic,
                    "time": position.time,
                    "time_update": position.time_update,
                }
            )

        return result

    # ------------------------------------------------------------------
    # GET SINGLE POSITION
    # ------------------------------------------------------------------

    def get_position(
        self,
        ticket: int,
    ) -> dict[str, Any] | None:

        if not self.ensure_connection():
            return None

        try:
            ticket = int(ticket)
        except (TypeError, ValueError):
            return None

        positions = mt5.positions_get(
            ticket=ticket
        )

        if not positions:
            return None

        position = positions[0]

        if position.magic != self.magic_number:
            return None

        if position.type == mt5.POSITION_TYPE_BUY:
            position_type = "buy"

        elif position.type == mt5.POSITION_TYPE_SELL:
            position_type = "sell"

        else:
            return None

        return {
            "ticket": position.ticket,
            "symbol": position.symbol,
            "type": position_type,
            "volume": position.volume,
            "entry_price": position.price_open,
            "current_price": position.price_current,
            "stop_loss": position.sl,
            "take_profit": position.tp,
            "profit": position.profit,
            "swap": position.swap,
            "magic": position.magic,
            "time": position.time,
            "time_update": position.time_update,
        }

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:

        positions = self.get_positions()

        total_profit = sum(
            float(position["profit"])
            for position in positions
        )

        total_volume = sum(
            float(position["volume"])
            for position in positions
        )

        return {
            "open_trades": len(positions),
            "total_volume": total_volume,
            "floating_profit": round(
                total_profit,
                2,
            ),
        }