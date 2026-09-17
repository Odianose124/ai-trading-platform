from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from threading import Event, RLock

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
