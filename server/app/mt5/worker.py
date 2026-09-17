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
