from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from threading import Event, RLock
from typing import Any

from app.mt5.runtime import MT5AccountRuntime

logger = logging.getLogger(__name__)


class MT5WorkerError(RuntimeError):
    """Raised when an account-scoped MT5 worker cannot operate safely."""


class MT5WorkerAccountMismatchError(MT5WorkerError):
    """Raised when the worker connects to the wrong MT5 account."""


@dataclass(frozen=True)
class MT5WorkerStatus:
    mt5_account_id: int
    user_id: int
    login: int
    server: str
    connected: bool
    terminal_running: bool


class MT5AccountWorker:
    """
    Owns the MetaTrader 5 connection for exactly one account runtime.

    This class is intended to live inside a dedicated worker process.
    The MetaTrader5 Python module is process-global, so account isolation
    depends on each worker process having exactly one account runtime.
    """

    MAGIC_NUMBER = 202609

    def __init__(
        self,
        runtime: MT5AccountRuntime,
        password: str,
    ) -> None:
        global mt5

        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise MT5WorkerError(
                "The MetaTrader5 Python package is not available "
                "inside the MT5 worker process."
            ) from exc

        self.mt5 = mt5
        self.runtime = runtime
        self._password = password
        self._terminal_process: subprocess.Popen[bytes] | None = None
        self._connected = False
        self._lock = RLock()
        self._stop_event = Event()

    # ------------------------------------------------------------------
    # START
    # ------------------------------------------------------------------

    def start(self) -> MT5WorkerStatus:
        """
        Start the isolated terminal runtime and connect to its account.
        """

        with self._lock:
            if self._connected:
                return self.status()

            self.runtime.validate()

            self._stop_event.clear()

            self._start_terminal()
            self._initialize_mt5()
            self._verify_account()

            self._connected = True

            logger.info(
                "MT5 account worker connected | "
                "mt5_account_id=%s | user_id=%s | login=%s | server=%s",
                self.runtime.mt5_account_id,
                self.runtime.user_id,
                self.runtime.login,
                self.runtime.server,
            )

            return self.status()

    # ------------------------------------------------------------------
    # TERMINAL
    # ------------------------------------------------------------------

    def _start_terminal(self) -> None:
        """
        Start the terminal assigned to this account runtime.

        The terminal runs in portable mode so its runtime data remains
        isolated inside its own runtime directory.
        """

        if self._terminal_process is not None:
            if self._terminal_process.poll() is None:
                return

            self._terminal_process = None

        command = [
            str(self.runtime.terminal_path),
            "/portable",
        ]

        try:
            self._terminal_process = subprocess.Popen(
                command,
                cwd=str(self.runtime.runtime_directory),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(
                    subprocess,
                    "CREATE_NO_WINDOW",
                    0,
                ),
            )
        except OSError as exc:
            raise MT5WorkerError(
                "Unable to start the MT5 terminal for account "
                f"{self.runtime.mt5_account_id}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # INITIALIZE
    # ------------------------------------------------------------------

    def _initialize_mt5(self) -> None:
        """
        Initialize MetaTrader 5 against this worker's terminal.

        The password is supplied only for this connection attempt.
        It is intentionally not stored in the database or runtime
        identity. The worker process keeps it only in memory.
        """

        initialized = mt5.initialize(
            path=str(self.runtime.terminal_path),
            login=self.runtime.login,
            password=self._password,
            server=self.runtime.server,
        )

        if not initialized:
            error = mt5.last_error()

            self._shutdown_terminal()

            raise MT5WorkerError(
                "MetaTrader 5 initialization failed for account "
                f"{self.runtime.mt5_account_id}: {error}"
            )

        terminal_info = mt5.terminal_info()
        account_info = mt5.account_info()

        if terminal_info is None:
            error = mt5.last_error()
            mt5.shutdown()
            self._shutdown_terminal()

            raise MT5WorkerError(
                "Unable to read MT5 terminal information for account "
                f"{self.runtime.mt5_account_id}: {error}"
            )

        if account_info is None:
            error = mt5.last_error()
            mt5.shutdown()
            self._shutdown_terminal()

            raise MT5WorkerError(
                "Unable to read MT5 account information for account "
                f"{self.runtime.mt5_account_id}: {error}"
            )

    # ------------------------------------------------------------------
    # ACCOUNT VERIFICATION
    # ------------------------------------------------------------------

    def _verify_account(self) -> None:
        account_info = mt5.account_info()

        if account_info is None:
            raise MT5WorkerError(
                "MT5 account information is unavailable after initialization."
            )

        actual_login = int(account_info.login)
        actual_server = str(account_info.server).strip()

        if actual_login != self.runtime.login:
            mt5.shutdown()
            self._shutdown_terminal()

            raise MT5WorkerAccountMismatchError(
                "The MT5 terminal connected to an unexpected account. "
                f"Expected login {self.runtime.login}, "
                f"received {actual_login}."
            )

        if actual_server.lower() != self.runtime.server.lower():
            mt5.shutdown()
            self._shutdown_terminal()

            raise MT5WorkerAccountMismatchError(
                "The MT5 terminal connected to an unexpected server. "
                f"Expected server {self.runtime.server}, "
                f"received {actual_server}."
            )

    # ------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------

    def status(self) -> MT5WorkerStatus:
        account_info = mt5.account_info()

        terminal_running = (
            self._terminal_process is not None
            and self._terminal_process.poll() is None
        )

        connected = (
            self._connected
            and account_info is not None
            and int(account_info.login) == self.runtime.login
            and str(account_info.server).strip().lower()
            == self.runtime.server.lower()
        )

        return MT5WorkerStatus(
            mt5_account_id=self.runtime.mt5_account_id,
            user_id=self.runtime.user_id,
            login=self.runtime.login,
            server=self.runtime.server,
            connected=connected,
            terminal_running=terminal_running,
        )

    # ------------------------------------------------------------------
    # POSITIONS
    # ------------------------------------------------------------------

    def get_positions(
        self,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Read platform-owned positions from this account's MT5 session.

        This method runs only inside the account's dedicated worker
        process. It never initializes MT5 and never sends an order.
        """

        if not self.status().connected:
            raise MT5WorkerError(
                "The MT5 account worker is not connected."
            )

        positions = mt5.positions_get()

        if positions is None:
            error = mt5.last_error()

            raise MT5WorkerError(
                "Unable to read MT5 positions: "
                f"{error}"
            )

        normalized_symbol = (
            symbol.strip().upper()
            if symbol
            else None
        )

        result: list[dict[str, Any]] = []

        for position in positions:
            if position.magic != self.MAGIC_NUMBER:
                continue

            if (
                normalized_symbol
                and str(position.symbol).upper()
                != normalized_symbol
            ):
                continue

            result.append(
                self._serialize_position(position)
            )

        return result

    def get_pending_orders(
        self,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Read platform-owned pending orders from this account's MT5 session.

        The current market price is read from the same account-scoped
        MT5 worker so pending-order data remains isolated per account.
        """

        if not self.status().connected:
            raise MT5WorkerError(
                "The MT5 account worker is not connected."
            )

        orders = mt5.orders_get()

        if orders is None:
            error = mt5.last_error()

            raise MT5WorkerError(
                "Unable to read MT5 pending orders: "
                f"{error}"
            )

        normalized_symbol = (
            symbol.strip().upper()
            if symbol
            else None
        )

        pending_types = {
            mt5.ORDER_TYPE_BUY_LIMIT: "buy_limit",
            mt5.ORDER_TYPE_SELL_LIMIT: "sell_limit",
            mt5.ORDER_TYPE_BUY_STOP: "buy_stop",
            mt5.ORDER_TYPE_SELL_STOP: "sell_stop",
        }

        result: list[dict[str, Any]] = []

        for order in orders:
            if order.magic != self.MAGIC_NUMBER:
                continue

            order_type = pending_types.get(order.type)

            if order_type is None:
                continue

            order_symbol = str(order.symbol)

            if (
                normalized_symbol
                and order_symbol.upper()
                != normalized_symbol
            ):
                continue

            tick = mt5.symbol_info_tick(order_symbol)

            if tick is None:
                error = mt5.last_error()

                raise MT5WorkerError(
                    "Unable to read current market price for "
                    f"{order_symbol}: {error}"
                )

            if order_type in {
                "buy_limit",
                "buy_stop",
            }:
                current_price = float(tick.ask)
            else:
                current_price = float(tick.bid)

            result.append(
                {
                    "ticket": int(order.ticket),
                    "symbol": order_symbol,
                    "type": order_type,
                    "volume": float(order.volume_current),
                    "price": float(order.price_open),
                    "current_price": current_price,
                    "bid": float(tick.bid),
                    "ask": float(tick.ask),
                    "sl": float(order.sl),
                    "tp": float(order.tp),
                    "magic": int(order.magic),
                    "time_setup": (
                        int(order.time_setup)
                        if order.time_setup
                        else None
                    ),
                    "time_setup_msc": (
                        int(order.time_setup_msc)
                        if order.time_setup_msc
                        else None
                    ),
                    "time_expiration": (
                        int(order.time_expiration)
                        if order.time_expiration
                        else None
                    ),
                    "type_time": int(order.type_time),
                    "type_filling": int(order.type_filling),
                    "state": int(order.state),
                    "comment": str(order.comment),
                }
            )

        return result

    def cancel_pending_order(
        self,
        ticket: int,
    ) -> dict[str, Any]:
        """
        Cancel one platform-owned pending order through this
        account's isolated MT5 session.
        """

        if not self.status().connected:
            raise MT5WorkerError(
                "The MT5 account worker is not connected."
            )

        try:
            normalized_ticket = int(ticket)
        except (TypeError, ValueError) as exc:
            raise MT5WorkerError(
                "Pending-order ticket must be an integer."
            ) from exc

        orders = mt5.orders_get(
            ticket=normalized_ticket,
        )

        if orders is None:
            raise MT5WorkerError(
                "Unable to read MT5 pending order: "
                f"{mt5.last_error()}"
            )

        if not orders:
            raise MT5WorkerError(
                f"Pending order {normalized_ticket} was not found."
            )

        order = orders[0]

        if order.magic != self.MAGIC_NUMBER:
            raise MT5WorkerError(
                "The pending order does not belong to this platform."
            )

        pending_types = {
            mt5.ORDER_TYPE_BUY_LIMIT,
            mt5.ORDER_TYPE_SELL_LIMIT,
            mt5.ORDER_TYPE_BUY_STOP,
            mt5.ORDER_TYPE_SELL_STOP,
        }

        if order.type not in pending_types:
            raise MT5WorkerError(
                "The specified ticket is not a pending order."
            )

        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": normalized_ticket,
        }

        result = mt5.order_send(request)

        if result is None:
            raise MT5WorkerError(
                "MT5 pending-order cancellation returned no result: "
                f"{mt5.last_error()}"
            )

        return {
            "retcode": getattr(result, "retcode", None),
            "comment": getattr(result, "comment", None),
            "request_id": getattr(result, "request_id", None),
            "order": getattr(result, "order", None),
            "deal": getattr(result, "deal", None),
            "volume": getattr(result, "volume", None),
            "price": getattr(result, "price", None),
            "bid": getattr(result, "bid", None),
            "ask": getattr(result, "ask", None),
            "retcode_external": getattr(
                result,
                "retcode_external",
                None,
            ),
            "last_error": mt5.last_error(),
        }

    def modify_pending_order(
        self,
        ticket: int,
        price: Any = None,
        stop_loss: Any = None,
        take_profit: Any = None,
    ) -> dict[str, Any]:
        """
        Modify one platform-owned pending order through this account's
        isolated MT5 session.
        """

        if not self.status().connected:
            raise MT5WorkerError(
                "The MT5 account worker is not connected."
            )

        try:
            normalized_ticket = int(ticket)
        except (TypeError, ValueError) as exc:
            raise MT5WorkerError(
                "Pending-order ticket must be an integer."
            ) from exc

        orders = mt5.orders_get(
            ticket=normalized_ticket,
        )

        if orders is None:
            raise MT5WorkerError(
                "Unable to read MT5 pending order: "
                f"{mt5.last_error()}"
            )

        if not orders:
            raise MT5WorkerError(
                f"Pending order {normalized_ticket} was not found."
            )

        order = orders[0]

        if order.magic != self.MAGIC_NUMBER:
            raise MT5WorkerError(
                "The pending order does not belong to this platform."
            )

        pending_types = {
            mt5.ORDER_TYPE_BUY_LIMIT,
            mt5.ORDER_TYPE_SELL_LIMIT,
            mt5.ORDER_TYPE_BUY_STOP,
            mt5.ORDER_TYPE_SELL_STOP,
        }

        if order.type not in pending_types:
            raise MT5WorkerError(
                "The specified ticket is not a pending order."
            )

        try:
            final_price = (
                float(price)
                if price is not None
                else float(order.price_open)
            )
        except (TypeError, ValueError) as exc:
            raise MT5WorkerError(
                "Pending-order price must be numeric."
            ) from exc

        if final_price <= 0:
            raise MT5WorkerError(
                "Pending-order price must be greater than zero."
            )

        def normalize_stop(value, existing):
            if value is None:
                return float(existing)

            try:
                normalized = float(value)
            except (TypeError, ValueError) as exc:
                raise MT5WorkerError(
                    "Pending-order stop-loss/take-profit "
                    "values must be numeric."
                ) from exc

            if normalized < 0:
                raise MT5WorkerError(
                    "Pending-order stop-loss/take-profit "
                    "values cannot be negative."
                )

            return normalized

        final_stop_loss = normalize_stop(
            stop_loss,
            order.sl,
        )

        final_take_profit = normalize_stop(
            take_profit,
            order.tp,
        )

        request = {
            "action": mt5.TRADE_ACTION_MODIFY,
            "order": normalized_ticket,
            "symbol": str(order.symbol),
            "price": final_price,
            "sl": final_stop_loss,
            "tp": final_take_profit,
            "type_time": int(order.type_time),
        }

        if getattr(order, "time_expiration", 0):
            request["expiration"] = int(
                order.time_expiration
            )

        result = mt5.order_send(request)

        if result is None:
            raise MT5WorkerError(
                "MT5 pending-order modification returned no result: "
                f"{mt5.last_error()}"
            )

        return {
            "retcode": getattr(result, "retcode", None),
            "comment": getattr(result, "comment", None),
            "request_id": getattr(result, "request_id", None),
            "order": getattr(result, "order", None),
            "deal": getattr(result, "deal", None),
            "volume": getattr(result, "volume", None),
            "price": getattr(result, "price", None),
            "bid": getattr(result, "bid", None),
            "ask": getattr(result, "ask", None),
            "retcode_external": getattr(
                result,
                "retcode_external",
                None,
            ),
            "last_error": mt5.last_error(),
        }

    def get_position(
        self,
        ticket: int,
    ) -> dict[str, Any] | None:
        """
        Read one platform-owned position from this account's MT5 session.
        """

        if not self.status().connected:
            raise MT5WorkerError(
                "The MT5 account worker is not connected."
            )

        try:
            normalized_ticket = int(ticket)
        except (TypeError, ValueError) as exc:
            raise MT5WorkerError(
                "Position ticket must be an integer."
            ) from exc

        positions = mt5.positions_get(
            ticket=normalized_ticket,
        )

        if positions is None:
            error = mt5.last_error()

            raise MT5WorkerError(
                "Unable to read MT5 position: "
                f"{error}"
            )

        if not positions:
            return None

        position = positions[0]

        if position.magic != self.MAGIC_NUMBER:
            return None

        return self._serialize_position(position)

    def get_position_summary(self) -> dict[str, Any]:
        """
        Produce an account-scoped summary of platform-owned positions.
        """

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

    # ------------------------------------------------------------------
    # BROKER VALIDATION
    # ------------------------------------------------------------------

    def validate_trade(
        self,
        *,
        symbol: str,
        direction: str,
        volume: Any,
        entry_price: Any = None,
        stop_loss: Any = None,
        take_profit: Any = None,
        order_type: Any = None,
    ) -> dict[str, Any]:
        """
        Run broker validation inside this account's isolated MT5 worker.
        """

        if not self.status().connected:
            raise MT5WorkerError(
                "The MT5 account worker is not connected."
            )

        from app.services.broker_validation_service import (
            BrokerValidationService,
        )

        validator = BrokerValidationService(
            mt5_module=self.mt5,
            connection=None,
        )

        result = validator.validate(
            symbol=symbol,
            direction=direction,
            volume=volume,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            order_type=order_type,
        )

        return result.serialize()

    # ------------------------------------------------------------------
    # HISTORY
    # ------------------------------------------------------------------

    def get_order_history(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        """
        Read platform-owned MT5 order and deal history for this account.

        Historical orders expose placement/execution/cancellation state,
        while historical deals expose actual trade executions and their
        realized profit/loss. Both are filtered by this platform's magic
        number inside the isolated account worker.
        """

        if not self.status().connected:
            raise MT5WorkerError(
                "The MT5 account worker is not connected."
            )

        final_date_to = date_to or datetime.now(timezone.utc)
        final_date_from = date_from or (
            final_date_to - timedelta(days=30)
        )

        if final_date_from.tzinfo is None:
            final_date_from = final_date_from.replace(
                tzinfo=timezone.utc
            )

        if final_date_to.tzinfo is None:
            final_date_to = final_date_to.replace(
                tzinfo=timezone.utc
            )

        if final_date_from > final_date_to:
            raise MT5WorkerError(
                "History start time cannot be later than end time."
            )

        normalized_symbol = (
            symbol.strip().upper()
            if symbol
            else None
        )

        orders = mt5.history_orders_get(
            final_date_from,
            final_date_to,
        )

        if orders is None:
            raise MT5WorkerError(
                "Unable to read MT5 order history: "
                f"{mt5.last_error()}"
            )

        deals = mt5.history_deals_get(
            final_date_from,
            final_date_to,
        )

        if deals is None:
            raise MT5WorkerError(
                "Unable to read MT5 deal history: "
                f"{mt5.last_error()}"
            )

        order_types = {
            mt5.ORDER_TYPE_BUY: "buy",
            mt5.ORDER_TYPE_SELL: "sell",
            mt5.ORDER_TYPE_BUY_LIMIT: "buy_limit",
            mt5.ORDER_TYPE_SELL_LIMIT: "sell_limit",
            mt5.ORDER_TYPE_BUY_STOP: "buy_stop",
            mt5.ORDER_TYPE_SELL_STOP: "sell_stop",
            mt5.ORDER_TYPE_BUY_STOP_LIMIT: "buy_stop_limit",
            mt5.ORDER_TYPE_SELL_STOP_LIMIT: "sell_stop_limit",
            mt5.ORDER_TYPE_CLOSE_BY: "close_by",
        }

        order_states = {
            mt5.ORDER_STATE_STARTED: "started",
            mt5.ORDER_STATE_PLACED: "placed",
            mt5.ORDER_STATE_CANCELED: "canceled",
            mt5.ORDER_STATE_PARTIAL: "partial",
            mt5.ORDER_STATE_FILLED: "filled",
            mt5.ORDER_STATE_REJECTED: "rejected",
            mt5.ORDER_STATE_EXPIRED: "expired",
            mt5.ORDER_STATE_REQUEST_ADD: "request_add",
            mt5.ORDER_STATE_REQUEST_MODIFY: "request_modify",
            mt5.ORDER_STATE_REQUEST_CANCEL: "request_cancel",
        }

        deal_types = {
            mt5.DEAL_TYPE_BUY: "buy",
            mt5.DEAL_TYPE_SELL: "sell",
        }

        deal_entries = {
            mt5.DEAL_ENTRY_IN: "in",
            mt5.DEAL_ENTRY_OUT: "out",
            mt5.DEAL_ENTRY_INOUT: "inout",
            mt5.DEAL_ENTRY_OUT_BY: "out_by",
        }

        history_orders: list[dict[str, Any]] = []
        history_deals: list[dict[str, Any]] = []

        for order in orders:
            if int(getattr(order, "magic", 0)) != self.MAGIC_NUMBER:
                continue

            order_symbol = str(getattr(order, "symbol", ""))

            if (
                normalized_symbol
                and order_symbol.upper() != normalized_symbol
            ):
                continue

            order_type_value = int(getattr(order, "type", 0))
            state_value = int(getattr(order, "state", 0))

            history_orders.append(
                {
                    "ticket": int(order.ticket),
                    "position_id": int(
                        getattr(order, "position_id", 0)
                    ),
                    "position_by_id": int(
                        getattr(order, "position_by_id", 0)
                    ),
                    "symbol": order_symbol,
                    "type": order_types.get(
                        order_type_value,
                        str(order_type_value),
                    ),
                    "state": order_states.get(
                        state_value,
                        str(state_value),
                    ),
                    "volume_initial": float(
                        getattr(order, "volume_initial", 0)
                    ),
                    "volume_current": float(
                        getattr(order, "volume_current", 0)
                    ),
                    "price_open": float(
                        getattr(order, "price_open", 0)
                    ),
                    "price_current": float(
                        getattr(order, "price_current", 0)
                    ),
                    "stop_loss": float(
                        getattr(order, "sl", 0)
                    ),
                    "take_profit": float(
                        getattr(order, "tp", 0)
                    ),
                    "price_stop_limit": float(
                        getattr(order, "price_stoplimit", 0)
                    ),
                    "time_setup": (
                        int(order.time_setup)
                        if getattr(order, "time_setup", 0)
                        else None
                    ),
                    "time_setup_msc": (
                        int(order.time_setup_msc)
                        if getattr(order, "time_setup_msc", 0)
                        else None
                    ),
                    "time_done": (
                        int(order.time_done)
                        if getattr(order, "time_done", 0)
                        else None
                    ),
                    "time_done_msc": (
                        int(order.time_done_msc)
                        if getattr(order, "time_done_msc", 0)
                        else None
                    ),
                    "time_expiration": (
                        int(order.time_expiration)
                        if getattr(order, "time_expiration", 0)
                        else None
                    ),
                    "type_time": int(
                        getattr(order, "type_time", 0)
                    ),
                    "type_filling": int(
                        getattr(order, "type_filling", 0)
                    ),
                    "reason": int(
                        getattr(order, "reason", 0)
                    ),
                    "magic": int(
                        getattr(order, "magic", 0)
                    ),
                    "comment": str(
                        getattr(order, "comment", "")
                    ),
                    "external_id": str(
                        getattr(order, "external_id", "")
                    ),
                }
            )

        for deal in deals:
            if int(getattr(deal, "magic", 0)) != self.MAGIC_NUMBER:
                continue

            deal_symbol = str(
                getattr(deal, "symbol", "")
            )

            if (
                normalized_symbol
                and deal_symbol.upper() != normalized_symbol
            ):
                continue

            deal_type_value = int(
                getattr(deal, "type", 0)
            )
            deal_entry_value = int(
                getattr(deal, "entry", 0)
            )

            event_type = (
                "position_closed"
                if deal_entry_value in {
                    mt5.DEAL_ENTRY_OUT,
                    mt5.DEAL_ENTRY_OUT_BY,
                }
                else "trade_execution"
            )

            history_deals.append(
                {
                    "ticket": int(deal.ticket),
                    "order_ticket": int(
                        getattr(deal, "order", 0)
                    ),
                    "position_id": int(
                        getattr(deal, "position_id", 0)
                    ),
                    "symbol": deal_symbol,
                    "type": deal_types.get(
                        deal_type_value,
                        str(deal_type_value),
                    ),
                    "entry": deal_entries.get(
                        deal_entry_value,
                        str(deal_entry_value),
                    ),
                    "event_type": event_type,
                    "volume": float(
                        getattr(deal, "volume", 0)
                    ),
                    "price": float(
                        getattr(deal, "price", 0)
                    ),
                    "profit": float(
                        getattr(deal, "profit", 0)
                    ),
                    "commission": float(
                        getattr(deal, "commission", 0)
                    ),
                    "swap": float(
                        getattr(deal, "swap", 0)
                    ),
                    "fee": float(
                        getattr(deal, "fee", 0)
                    ),
                    "time": (
                        int(deal.time)
                        if getattr(deal, "time", 0)
                        else None
                    ),
                    "time_msc": (
                        int(deal.time_msc)
                        if getattr(deal, "time_msc", 0)
                        else None
                    ),
                    "magic": int(
                        getattr(deal, "magic", 0)
                    ),
                    "reason": int(
                        getattr(deal, "reason", 0)
                    ),
                    "comment": str(
                        getattr(deal, "comment", "")
                    ),
                    "external_id": str(
                        getattr(deal, "external_id", "")
                    ),
                }
            )

        history_orders.sort(
            key=lambda item: (
                item.get("time_done")
                or item.get("time_setup")
                or 0
            ),
            reverse=True,
        )

        history_deals.sort(
            key=lambda item: item.get("time") or 0,
            reverse=True,
        )

        return {
            "date_from": final_date_from.isoformat(),
            "date_to": final_date_to.isoformat(),
            "orders": history_orders,
            "deals": history_deals,
            "closed_positions": [
                deal
                for deal in history_deals
                if deal["event_type"] == "position_closed"
            ],
            "count_orders": len(history_orders),
            "count_deals": len(history_deals),
        }

    def get_history_order_position_ids(
        self,
        order_ticket: int,
    ) -> list[int]:
        """
        Resolve position identities associated with one MT5 order ticket.

        The history query executes inside this account's dedicated worker
        process, so the result can never come from another account's
        process-global MT5 session.
        """

        if not self.status().connected:
            raise MT5WorkerError(
                "The MT5 account worker is not connected."
            )

        try:
            normalized_ticket = int(order_ticket)
        except (TypeError, ValueError) as exc:
            raise MT5WorkerError(
                "Order ticket must be an integer."
            ) from exc

        orders = mt5.history_orders_get(
            ticket=normalized_ticket,
        )

        if orders is None:
            error = mt5.last_error()

            raise MT5WorkerError(
                "Unable to read MT5 order history: "
                f"{error}"
            )

        position_ids: set[int] = set()

        for order in orders:
            position_id = getattr(
                order,
                "position_id",
                None,
            )

            if position_id:
                position_ids.add(int(position_id))

        return sorted(position_ids)

    def get_history_order_deal_position_ids(
        self,
        order_ticket: int,
    ) -> list[int]:
        """
        Resolve position identities associated with deals belonging to
        one MT5 order ticket.
        """

        if not self.status().connected:
            raise MT5WorkerError(
                "The MT5 account worker is not connected."
            )

        try:
            normalized_ticket = int(order_ticket)
        except (TypeError, ValueError) as exc:
            raise MT5WorkerError(
                "Order ticket must be an integer."
            ) from exc

        deals = mt5.history_deals_get(
            ticket=normalized_ticket,
        )

        if deals is None:
            error = mt5.last_error()

            raise MT5WorkerError(
                "Unable to read MT5 deal history: "
                f"{error}"
            )

        position_ids: set[int] = set()

        for deal in deals:
            position_id = getattr(
                deal,
                "position_id",
                None,
            )

            if position_id:
                position_ids.add(int(position_id))

        return sorted(position_ids)

    def get_history_deal_position_id(
        self,
        deal_ticket: int,
        date_from: datetime,
        date_to: datetime,
    ) -> int | None:
        """
        Find the position identity for one deal ticket inside the
        caller-provided execution-time history window.
        """

        if not self.status().connected:
            raise MT5WorkerError(
                "The MT5 account worker is not connected."
            )

        try:
            normalized_ticket = int(deal_ticket)
        except (TypeError, ValueError) as exc:
            raise MT5WorkerError(
                "Deal ticket must be an integer."
            ) from exc

        deals = mt5.history_deals_get(
            date_from,
            date_to,
        )

        if deals is None:
            error = mt5.last_error()

            raise MT5WorkerError(
                "Unable to read MT5 deal history: "
                f"{error}"
            )

        position_ids: set[int] = set()

        for deal in deals:
            if int(
                getattr(deal, "ticket", 0)
            ) != normalized_ticket:
                continue

            position_id = getattr(
                deal,
                "position_id",
                None,
            )

            if position_id:
                position_ids.add(int(position_id))

        if len(position_ids) != 1:
            return None

        return next(iter(position_ids))

    @staticmethod
    def _serialize_position(
        position: Any,
    ) -> dict[str, Any]:

        if position.type == mt5.POSITION_TYPE_BUY:
            position_type = "buy"

        elif position.type == mt5.POSITION_TYPE_SELL:
            position_type = "sell"

        else:
            raise MT5WorkerError(
                f"Unsupported MT5 position type: {position.type}"
            )

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
    # STOP
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """
        Stop this account's MT5 connection and terminal only.
        """

        with self._lock:
            self._stop_event.set()

            if self._connected:
                try:
                    mt5.shutdown()
                except Exception:
                    logger.exception(
                        "Error shutting down MT5 connection | "
                        "mt5_account_id=%s",
                        self.runtime.mt5_account_id,
                    )

            self._connected = False
            self._shutdown_terminal()

            logger.info(
                "MT5 account worker stopped | mt5_account_id=%s | user_id=%s",
                self.runtime.mt5_account_id,
                self.runtime.user_id,
            )

    # ------------------------------------------------------------------
    # TERMINAL SHUTDOWN
    # ------------------------------------------------------------------

    def _shutdown_terminal(self) -> None:
        process = self._terminal_process

        if process is None:
            return

        self._terminal_process = None

        if process.poll() is not None:
            return

        try:
            process.terminate()
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()

            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "MT5 terminal process did not exit after forced shutdown | "
                    "mt5_account_id=%s",
                    self.runtime.mt5_account_id,
                )
        except OSError:
            logger.exception(
                "Unable to stop MT5 terminal process | "
                "mt5_account_id=%s",
                self.runtime.mt5_account_id,
            )

    # ------------------------------------------------------------------
    # CONTEXT MANAGER
    # ------------------------------------------------------------------

    def __enter__(self) -> "MT5AccountWorker":
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # BROKER INFORMATION HELPERS
    # ------------------------------------------------------------------

    def symbol_info(
        self,
        symbol: str,
    ) -> dict[str, Any]:

        if not self.status().connected:
            raise MT5WorkerError(
                "The MT5 account worker is not connected."
            )

        info = mt5.symbol_info(symbol)

        if info is None:
            raise MT5WorkerError(
                "Unable to read symbol information: "
                f"{mt5.last_error()}"
            )

        return {
            "name": info.name,
            "visible": info.visible,
            "digits": info.digits,
            "point": info.point,
            "trade_tick_size": info.trade_tick_size,
            "trade_tick_value": info.trade_tick_value,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "filling_mode": info.filling_mode,
            "trade_exemode": info.trade_exemode,
        }

    def symbol_info_tick(
        self,
        symbol: str,
    ) -> dict[str, Any]:

        if not self.status().connected:
            raise MT5WorkerError(
                "The MT5 account worker is not connected."
            )

        tick = mt5.symbol_info_tick(symbol)

        if tick is None:
            raise MT5WorkerError(
                "Unable to read tick information: "
                f"{mt5.last_error()}"
            )

        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
            "time": tick.time,
        }

    def account_info(
        self,
    ) -> dict[str, Any]:

        if not self.status().connected:
            raise MT5WorkerError(
                "The MT5 account worker is not connected."
            )

        account = mt5.account_info()

        if account is None:
            raise MT5WorkerError(
                "Unable to read account information: "
                f"{mt5.last_error()}"
            )

        return {
            "login": account.login,
            "server": account.server,
            "balance": account.balance,
            "equity": account.equity,
            "margin": account.margin,
            "margin_free": account.margin_free,
            "margin_level": account.margin_level,
        }

    def order_calc_margin(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:

        if not self.status().connected:
            raise MT5WorkerError(
                "The MT5 account worker is not connected."
            )

        if not isinstance(request, dict):
            raise MT5WorkerError(
                "MT5 margin calculation request must be a dictionary."
            )

        normalized_request = self._normalize_order_request(
            request
        )

        order_type = normalized_request.get("order_type")

        if isinstance(order_type, str):
            order_type_mapping = {
                "BUY": mt5.ORDER_TYPE_BUY,
                "SELL": mt5.ORDER_TYPE_SELL,
            }

            normalized_order_type = order_type.strip().upper()

            if normalized_order_type not in order_type_mapping:
                raise MT5WorkerError(
                    f"Unsupported MT5 margin order type: {order_type}"
                )

            order_type = order_type_mapping[normalized_order_type]

        try:
            order_type = int(order_type)
        except (TypeError, ValueError) as exc:
            raise MT5WorkerError(
                "MT5 margin order type must be BUY, SELL, or an integer."
            ) from exc

        symbol = str(
            normalized_request.get("symbol", "")
        ).strip()

        if not symbol:
            raise MT5WorkerError(
                "MT5 margin calculation symbol is required."
            )

        try:
            volume = float(
                normalized_request.get("volume")
            )
        except (TypeError, ValueError) as exc:
            raise MT5WorkerError(
                "MT5 margin calculation volume must be numeric."
            ) from exc

        if volume <= 0:
            raise MT5WorkerError(
                "MT5 margin calculation volume must be greater than zero."
            )

        try:
            price = float(
                normalized_request.get("price")
            )
        except (TypeError, ValueError) as exc:
            raise MT5WorkerError(
                "MT5 margin calculation price must be numeric."
            ) from exc

        if price <= 0:
            raise MT5WorkerError(
                "MT5 margin calculation price must be greater than zero."
            )

        result = mt5.order_calc_margin(
            order_type,
            symbol,
            volume,
            price,
        )

        if result is None:
            raise MT5WorkerError(
                "Unable to calculate margin: "
                f"{mt5.last_error()}"
            )

        return {
            "margin": result,
        }

    def _normalize_order_request(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Convert platform-level semantic order values into MT5-native
        constants inside the isolated account worker.
        """

        final_request = dict(request)

        order_type = final_request.get("type")

        if isinstance(order_type, str):
            normalized_type = order_type.strip().upper()

            type_mapping = {
                "BUY": mt5.ORDER_TYPE_BUY,
                "SELL": mt5.ORDER_TYPE_SELL,
                "BUY_LIMIT": mt5.ORDER_TYPE_BUY_LIMIT,
                "BUY_STOP": mt5.ORDER_TYPE_BUY_STOP,
                "SELL_LIMIT": mt5.ORDER_TYPE_SELL_LIMIT,
                "SELL_STOP": mt5.ORDER_TYPE_SELL_STOP,
            }

            try:
                final_request["type"] = type_mapping[
                    normalized_type
                ]
            except KeyError as exc:
                raise MT5WorkerError(
                    f"Unsupported MT5 order type: {order_type}"
                ) from exc

        action = final_request.get("action")

        if isinstance(action, str):
            action_mapping = {
                "DEAL": mt5.TRADE_ACTION_DEAL,
                "PENDING": mt5.TRADE_ACTION_PENDING,
            }

            normalized_action = action.strip().upper()

            try:
                final_request["action"] = action_mapping[
                    normalized_action
                ]
            except KeyError as exc:
                raise MT5WorkerError(
                    f"Unsupported MT5 trade action: {action}"
                ) from exc

        filling = final_request.get("type_filling")

        if isinstance(filling, str):
            filling_mapping = {
                "FOK": mt5.ORDER_FILLING_FOK,
                "IOC": mt5.ORDER_FILLING_IOC,
                "RETURN": mt5.ORDER_FILLING_RETURN,
            }

            normalized_filling = filling.strip().upper()

            try:
                final_request["type_filling"] = filling_mapping[
                    normalized_filling
                ]
            except KeyError as exc:
                raise MT5WorkerError(
                    f"Unsupported MT5 filling mode: {filling}"
                ) from exc

        type_time = final_request.get("type_time")

        if isinstance(type_time, str):
            time_mapping = {
                "GTC": mt5.ORDER_TIME_GTC,
            }

            normalized_type_time = type_time.strip().upper()

            try:
                final_request["type_time"] = time_mapping[
                    normalized_type_time
                ]
            except KeyError as exc:
                raise MT5WorkerError(
                    f"Unsupported MT5 order time type: {type_time}"
                ) from exc

        broker_symbol = str(
            final_request.get("symbol", "")
        ).strip()

        if broker_symbol:
            symbol_info = mt5.symbol_info(
                broker_symbol
            )

            if symbol_info is None:
                raise MT5WorkerError(
                    "Unable to read MT5 symbol information for "
                    f"{broker_symbol}: {mt5.last_error()}"
                )

            market_execution = (
                int(
                    getattr(
                        symbol_info,
                        "trade_exemode",
                        0,
                    )
                    or 0
                )
                == getattr(
                    mt5,
                    "SYMBOL_TRADE_EXECUTION_MARKET",
                    2,
                )
            )

            if (
                str(
                    request.get("execution_mode", "")
                ).strip().lower()
                == "market"
                and market_execution
            ):
                final_request.pop("price", None)

        final_request.pop(
            "execution_mode",
            None,
        )

        return final_request

    @staticmethod
    def _retcode_description(
        retcode: int,
    ) -> str:
        descriptions = {
            getattr(
                mt5,
                "TRADE_RETCODE_DONE",
                -1,
            ): "Request completed successfully",
            getattr(
                mt5,
                "TRADE_RETCODE_PLACED",
                -1,
            ): "Order placed successfully",
            getattr(
                mt5,
                "TRADE_RETCODE_DONE_PARTIAL",
                -1,
            ): "Request partially completed",
            getattr(
                mt5,
                "TRADE_RETCODE_REQUOTE",
                -1,
            ): "Requote",
            getattr(
                mt5,
                "TRADE_RETCODE_REJECT",
                -1,
            ): "Request rejected",
            getattr(
                mt5,
                "TRADE_RETCODE_CANCEL",
                -1,
            ): "Request cancelled",
            getattr(
                mt5,
                "TRADE_RETCODE_INVALID",
                -1,
            ): "Invalid request",
            getattr(
                mt5,
                "TRADE_RETCODE_INVALID_VOLUME",
                -1,
            ): "Invalid volume",
            getattr(
                mt5,
                "TRADE_RETCODE_INVALID_PRICE",
                -1,
            ): "Invalid price",
            getattr(
                mt5,
                "TRADE_RETCODE_INVALID_STOPS",
                -1,
            ): "Invalid stops",
            getattr(
                mt5,
                "TRADE_RETCODE_TRADE_DISABLED",
                -1,
            ): "Trading disabled",
            getattr(
                mt5,
                "TRADE_RETCODE_MARKET_CLOSED",
                -1,
            ): "Market closed",
            getattr(
                mt5,
                "TRADE_RETCODE_NO_MONEY",
                -1,
            ): "Insufficient money",
            getattr(
                mt5,
                "TRADE_RETCODE_PRICE_CHANGED",
                -1,
            ): "Price changed",
            getattr(
                mt5,
                "TRADE_RETCODE_PRICE_OFF",
                -1,
            ): "No price available",
            getattr(
                mt5,
                "TRADE_RETCODE_INVALID_FILL",
                -1,
            ): "Invalid filling mode",
        }

        return descriptions.get(
            retcode,
            f"MT5 retcode {retcode}",
        )
    # ORDER PREFLIGHT CHECK
    # ------------------------------------------------------------------

    def order_check(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Validate an MT5 order request without sending it.

        Runs only inside the account-scoped worker process.
        """

        if not self.status().connected:
            raise MT5WorkerError(
                "The MT5 account worker is not connected."
            )

        if not isinstance(request, dict):
            raise MT5WorkerError(
                "MT5 order check request must be a dictionary."
            )

        normalized_request = self._normalize_order_request(
            request
        )

        result = mt5.order_check(
            normalized_request
        )

        if result is None:
            raise MT5WorkerError(
                "MT5 order_check returned no result: "
                f"{mt5.last_error()}"
            )

        retcode = getattr(result, "retcode", None)

        accepted_retcodes = {
            getattr(mt5, "TRADE_RETCODE_DONE", -999999),
            getattr(mt5, "TRADE_RETCODE_PLACED", -999998),
            getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", -999997),
        }

        return {
            "retcode": retcode,
            "retcode_description": self._retcode_description(retcode),
            "accepted": retcode in accepted_retcodes,
            "comment": getattr(result, "comment", None),
            "balance": getattr(result, "balance", None),
            "equity": getattr(result, "equity", None),
            "margin": getattr(result, "margin", None),
            "margin_free": getattr(result, "margin_free", None),
            "margin_level": getattr(result, "margin_level", None),
        }
    # ------------------------------------------------------------------
    # ORDER EXECUTION
    # ------------------------------------------------------------------

    def execute_order(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute one already-authorized MT5 trade request.

        This method runs only inside the account-scoped worker process.
        The parent FastAPI process never calls mt5.order_send() directly.

        The request must already contain the final broker-approved MT5
        order parameters. This method is responsible only for the final
        broker interaction and result serialization.
        """

        if not self.status().connected:
            raise MT5WorkerError(
                "The MT5 account worker is not connected."
            )

        if not isinstance(request, dict):
            raise MT5WorkerError(
                "MT5 order request must be a dictionary."
            )

        broker_symbol = str(
            request.get("symbol", "")
        ).strip()

        if not broker_symbol:
            raise MT5WorkerError(
                "MT5 order symbol is required."
            )

        try:
            volume = float(
                request.get("volume")
            )
        except (TypeError, ValueError) as exc:
            raise MT5WorkerError(
                "MT5 order volume must be numeric."
            ) from exc

        if volume <= 0:
            raise MT5WorkerError(
                "MT5 order volume must be greater than zero."
            )

        normalized_request = self._normalize_order_request(
            request
        )

        try:
            order_type = int(
                normalized_request.get("type")
            )
        except (TypeError, ValueError) as exc:
            raise MT5WorkerError(
                "MT5 order type must be an integer after normalization."
            ) from exc

        trade_action = normalized_request.get(
            "action",
            mt5.TRADE_ACTION_DEAL,
        )

        try:
            trade_action = int(trade_action)
        except (TypeError, ValueError) as exc:
            raise MT5WorkerError(
                "MT5 trade action must be an integer after normalization."
            ) from exc

        symbol_info = mt5.symbol_info(
            broker_symbol
        )

        if symbol_info is None:
            error = mt5.last_error()

            raise MT5WorkerError(
                "Unable to read MT5 symbol information for "
                f"{broker_symbol}: {error}"
            )

        if not symbol_info.visible:
            selected = mt5.symbol_select(
                broker_symbol,
                True,
            )

            if not selected:
                error = mt5.last_error()

                raise MT5WorkerError(
                    "Unable to select MT5 symbol "
                    f"{broker_symbol}: {error}"
                )

        final_request = dict(normalized_request)

        final_request["symbol"] = broker_symbol
        final_request["volume"] = volume
        final_request["type"] = order_type
        final_request["action"] = trade_action

        result = mt5.order_send(
            final_request
        )

        if result is None:
            error = mt5.last_error()

            raise MT5WorkerError(
                "MT5 order_send returned no result: "
                f"MT5 last_error={error}"
            )

        retcode = getattr(
            result,
            "retcode",
            None,
        )

        accepted_retcodes = {
            getattr(
                mt5,
                "TRADE_RETCODE_DONE",
                -999999,
            ),
            getattr(
                mt5,
                "TRADE_RETCODE_PLACED",
                -999998,
            ),
            getattr(
                mt5,
                "TRADE_RETCODE_DONE_PARTIAL",
                -999997,
            ),
        }

        return {
            "retcode": retcode,
            "retcode_description": self._retcode_description(
                retcode
            ),
            "accepted": retcode in accepted_retcodes,
            "comment": getattr(
                result,
                "comment",
                None,
            ),
            "request_id": getattr(
                result,
                "request_id",
                None,
            ),
            "order": getattr(
                result,
                "order",
                None,
            ),
            "deal": getattr(
                result,
                "deal",
                None,
            ),
            "volume": getattr(
                result,
                "volume",
                None,
            ),
            "price": getattr(
                result,
                "price",
                None,
            ),
            "bid": getattr(
                result,
                "bid",
                None,
            ),
            "ask": getattr(
                result,
                "ask",
                None,
            ),
            "retcode_external": getattr(
                result,
                "retcode_external",
                None,
            ),
            "last_error": mt5.last_error(),
        }








