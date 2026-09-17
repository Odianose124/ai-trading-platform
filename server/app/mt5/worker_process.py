from __future__ import annotations

import logging
import multiprocessing
from multiprocessing.connection import Connection
from threading import RLock
from typing import Any

from app.mt5.runtime import MT5AccountRuntime
from app.mt5.worker import MT5AccountWorker

logger = logging.getLogger(__name__)


class MT5WorkerProcessError(RuntimeError):
    """Raised when an MT5 worker process cannot be controlled safely."""


def _worker_process_entry(
    runtime: MT5AccountRuntime,
    connection: Connection,
) -> None:
    """
    Entry point executed inside the dedicated MT5 worker process.

    The MetaTrader5 Python module is loaded only inside this process.
    """

    worker = MT5AccountWorker(runtime)

    try:
        worker.start()

        connection.send(
            {
                "type": "started",
                "status": worker.status(),
            }
        )

        while True:
            try:
                command = connection.recv()
            except EOFError:
                break

            if not isinstance(command, dict):
                connection.send(
                    {
                        "type": "error",
                        "error": "Invalid worker command.",
                    }
                )
                continue

            action = command.get("action")

            if action == "status":
                connection.send(
                    {
                        "type": "status",
                        "status": worker.status(),
                    }
                )
                continue

            if action == "get_positions":
                symbol = command.get("symbol")

                if symbol is not None and not isinstance(symbol, str):
                    connection.send(
                        {
                            "type": "error",
                            "error": (
                                "The position symbol must be "
                                "a string or null."
                            ),
                        }
                    )
                    continue

                connection.send(
                    {
                        "type": "positions",
                        "positions": worker.get_positions(symbol),
                    }
                )
                continue

            if action == "get_position":
                ticket = command.get("ticket")

                try:
                    ticket = int(ticket)
                except (TypeError, ValueError):
                    connection.send(
                        {
                            "type": "error",
                            "error": (
                                "The position ticket must be an integer."
                            ),
                        }
                    )
                    continue

                connection.send(
                    {
                        "type": "position",
                        "position": worker.get_position(ticket),
                    }
                )
                continue

            if action == "get_position_summary":
                connection.send(
                    {
                        "type": "position_summary",
                        "summary": worker.get_position_summary(),
                    }
                )
                continue

            if action == "stop":
                worker.stop()

                connection.send(
                    {
                        "type": "stopped",
                    }
                )
                break

            connection.send(
                {
                    "type": "error",
                    "error": f"Unsupported worker action: {action}",
                }
            )

    except Exception as exc:
        logger.exception(
            "MT5 worker process failed | mt5_account_id=%s",
            runtime.mt5_account_id,
        )

        try:
            connection.send(
                {
                    "type": "error",
                    "error": str(exc),
                }
            )
        except (BrokenPipeError, EOFError, OSError):
            pass

    finally:
        try:
            worker.stop()
        except Exception:
            logger.exception(
                "Failed to cleanly stop MT5 worker | mt5_account_id=%s",
                runtime.mt5_account_id,
            )

        try:
            connection.close()
        except OSError:
            pass


class MT5WorkerProcess:
    """
    Parent-process controller for one account-scoped MT5 worker.

    Exactly one MT5AccountRuntime is associated with this process.
    """

    def __init__(
        self,
        runtime: MT5AccountRuntime,
    ) -> None:
        self.runtime = runtime
        self._process: multiprocessing.Process | None = None
        self._connection: Connection | None = None
        self._lock = RLock()

    @property
    def process(self) -> multiprocessing.Process | None:
        return self._process

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self.is_running():
                return self.status()

            self.runtime.validate()

            parent_connection, child_connection = (
                multiprocessing.Pipe()
            )

            process = multiprocessing.Process(
                target=_worker_process_entry,
                args=(
                    self.runtime,
                    child_connection,
                ),
                name=(
                    f"mt5-worker-"
                    f"{self.runtime.mt5_account_id}"
                ),
                daemon=True,
            )

            process.start()
            child_connection.close()

            self._process = process
            self._connection = parent_connection

            try:
                response = self._receive_response()
            except Exception:
                self._cleanup_failed_start()
                raise

            if response.get("type") == "error":
                self._cleanup_failed_start()

                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker failed to start.",
                    )
                )

            if response.get("type") != "started":
                self._cleanup_failed_start()

                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected startup response."
                )

            return self._serialize_status(
                response.get("status")
            )

    def status(self) -> dict[str, Any]:
        with self._lock:
            if not self.is_running():
                return {
                    "running": False,
                    "mt5_account_id": self.runtime.mt5_account_id,
                    "user_id": self.runtime.user_id,
                    "login": self.runtime.login,
                    "server": self.runtime.server,
                    "connected": False,
                    "terminal_running": False,
                }

            self._send_command(
                {
                    "action": "status",
                }
            )

            response = self._receive_response()

            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker status request failed.",
                    )
                )

            if response.get("type") != "status":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected status response."
                )

            return self._serialize_status(
                response.get("status")
            )

    def get_positions(
        self,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Request account-scoped positions from the dedicated worker.

        The actual MetaTrader5 API call executes inside the worker
        process, never inside the FastAPI parent process.
        """

        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )

            normalized_symbol = (
                symbol.strip().upper()
                if symbol
                else None
            )

            self._send_command(
                {
                    "action": "get_positions",
                    "symbol": normalized_symbol,
                }
            )

            response = self._receive_response()

            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker position request failed.",
                    )
                )

            if response.get("type") != "positions":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected position response."
                )

            positions = response.get("positions")

            if not isinstance(positions, list):
                raise MT5WorkerProcessError(
                    "MT5 worker returned an invalid positions payload."
                )

            return positions

    def get_position(
        self,
        ticket: int,
    ) -> dict[str, Any] | None:
        """
        Request one account-scoped position from the dedicated worker.
        """

        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )

            try:
                normalized_ticket = int(ticket)
            except (TypeError, ValueError) as exc:
                raise MT5WorkerProcessError(
                    "Position ticket must be an integer."
                ) from exc

            self._send_command(
                {
                    "action": "get_position",
                    "ticket": normalized_ticket,
                }
            )

            response = self._receive_response()

            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker position request failed.",
                    )
                )

            if response.get("type") != "position":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected "
                    "single-position response."
                )

            position = response.get("position")

            if position is not None and not isinstance(
                position,
                dict,
            ):
                raise MT5WorkerProcessError(
                    "MT5 worker returned an invalid position payload."
                )

            return position

    def get_position_summary(self) -> dict[str, Any]:
        """
        Request an account-scoped position summary.
        """

        with self._lock:
            if not self.is_running():
                raise MT5WorkerProcessError(
                    "MT5 worker process is not running."
                )

            self._send_command(
                {
                    "action": "get_position_summary",
                }
            )

            response = self._receive_response()

            if response.get("type") == "error":
                raise MT5WorkerProcessError(
                    response.get(
                        "error",
                        "MT5 worker position summary request failed.",
                    )
                )

            if response.get("type") != "position_summary":
                raise MT5WorkerProcessError(
                    "MT5 worker returned an unexpected "
                    "position summary response."
                )

            summary = response.get("summary")

            if not isinstance(summary, dict):
                raise MT5WorkerProcessError(
                    "MT5 worker returned an invalid position summary."
                )

            return summary

    def stop(self) -> None:
        with self._lock:
            process = self._process

            if process is None:
                return

            if process.is_alive():
                try:
                    self._send_command(
                        {
                            "action": "stop",
                        }
                    )

                    self._receive_response()
                except (
                    BrokenPipeError,
                    EOFError,
                    OSError,
                    MT5WorkerProcessError,
                ):
                    logger.warning(
                        "MT5 worker stopped without a normal response | "
                        "mt5_account_id=%s",
                        self.runtime.mt5_account_id,
                    )

            process.join(timeout=15)

            if process.is_alive():
                logger.warning(
                    "Terminating unresponsive MT5 worker | "
                    "mt5_account_id=%s",
                    self.runtime.mt5_account_id,
                )

                process.terminate()
                process.join(timeout=5)

            self._close_connection()

            self._process = None
            self._connection = None

    def is_running(self) -> bool:
        process = self._process

        return (
            process is not None
            and process.is_alive()
        )

    def _send_command(
        self,
        command: dict[str, Any],
    ) -> None:
        connection = self._connection

        if connection is None:
            raise MT5WorkerProcessError(
                "MT5 worker IPC connection is not available."
            )

        try:
            connection.send(command)
        except (BrokenPipeError, EOFError, OSError) as exc:
            raise MT5WorkerProcessError(
                "Unable to communicate with the MT5 worker process."
            ) from exc

    def _receive_response(self) -> dict[str, Any]:
        connection = self._connection

        if connection is None:
            raise MT5WorkerProcessError(
                "MT5 worker IPC connection is not available."
            )

        try:
            response = connection.recv()
        except (EOFError, OSError) as exc:
            raise MT5WorkerProcessError(
                "MT5 worker process closed the IPC connection."
            ) from exc

        if not isinstance(response, dict):
            raise MT5WorkerProcessError(
                "MT5 worker returned an invalid response."
            )

        return response

    def _serialize_status(
        self,
        status: Any,
    ) -> dict[str, Any]:
        if status is None:
            raise MT5WorkerProcessError(
                "MT5 worker returned no status."
            )

        if hasattr(status, "__dict__"):
            values = vars(status)
        elif isinstance(status, dict):
            values = status
        else:
            raise MT5WorkerProcessError(
                "MT5 worker returned an invalid status object."
            )

        return {
            "running": self.is_running(),
            **values,
        }

    def _cleanup_failed_start(self) -> None:
        process = self._process

        if process is not None:
            if process.is_alive():
                process.terminate()

            process.join(timeout=5)

        self._close_connection()

        self._process = None
        self._connection = None

    def _close_connection(self) -> None:
        connection = self._connection

        if connection is None:
            return

        try:
            connection.close()
        except OSError:
            pass


def create_worker_process(
    runtime: MT5AccountRuntime,
) -> MT5WorkerProcess:
    return MT5WorkerProcess(runtime)
