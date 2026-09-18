from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from threading import Event, RLock
from typing import Any

import MetaTrader5 as mt5

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

    def __init__(self, runtime: MT5AccountRuntime) -> None:
        self.runtime = runtime
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

        The password is intentionally omitted. The terminal is expected
        to have its authorized credentials saved in its own terminal
        runtime/database.
        """

        initialized = mt5.initialize(
            path=str(self.runtime.terminal_path),
            login=self.runtime.login,
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

        validator = BrokerValidationService()

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

        result = mt5.order_calc_margin(
            request["order_type"],
            request["symbol"],
            request["volume"],
            request["price"],
        )

        if result is None:
            raise MT5WorkerError(
                "Unable to calculate margin: "
                f"{mt5.last_error()}"
            )

        return {
            "margin": result,
        }

    # ------------------------------------------------------------------
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

        result = mt5.order_check(request)

        if result is None:
            raise MT5WorkerError(
                "MT5 order_check returned no result: "
                f"{mt5.last_error()}"
            )

        return {
            "retcode": getattr(result, "retcode", None),
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

        try:
            order_type = int(
                request.get("type")
            )
        except (TypeError, ValueError) as exc:
            raise MT5WorkerError(
                "MT5 order type must be an integer."
            ) from exc

        trade_action = request.get(
            "action",
            mt5.TRADE_ACTION_DEAL,
        )

        try:
            trade_action = int(trade_action)
        except (TypeError, ValueError) as exc:
            raise MT5WorkerError(
                "MT5 trade action must be an integer."
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

        final_request = dict(request)

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

        return {
            "retcode": getattr(
                result,
                "retcode",
                None,
            ),
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
