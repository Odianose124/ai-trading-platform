from __future__ import annotations

from threading import RLock
from typing import Any

from app.models.mt5_trading_account import MT5TradingAccount
from app.mt5.runtime_manager import (
    MT5RuntimeManagerError,
    mt5_runtime_manager,
)
from app.mt5.worker_process import (
    MT5WorkerProcess,
    MT5WorkerProcessError,
)


class MT5WorkerManagerError(RuntimeError):
    """Raised when an account worker cannot be managed safely."""


class MT5WorkerManager:
    """
    Owns the parent-process registry of account-scoped MT5 workers.

    Each MT5 account gets exactly one worker process in this FastAPI
    process. The worker process itself owns the MetaTrader 5 connection.
    """

    def __init__(self) -> None:
        self._workers: dict[int, MT5WorkerProcess] = {}
        self._lock = RLock()

    def start_account(
        self,
        account: MT5TradingAccount,
    ) -> dict[str, Any]:
        if account.id is None:
            raise MT5WorkerManagerError(
                "MT5 trading account must have a database ID."
            )

        if account.user_id is None:
            raise MT5WorkerManagerError(
                "MT5 trading account must belong to a user."
            )

        with self._lock:
            runtime = mt5_runtime_manager.register_account(account)

            existing = self._workers.get(account.id)

            if existing is not None:
                if existing.runtime.identity() != runtime.identity():
                    raise MT5WorkerManagerError(
                        "The existing worker identity does not match "
                        "the requested MT5 account."
                    )

                if existing.is_running():
                    return existing.status()

                self._workers.pop(account.id, None)

            worker = MT5WorkerProcess(runtime)

            try:
                status = worker.start()
            except (
                MT5WorkerProcessError,
                MT5RuntimeManagerError,
            ) as exc:
                raise MT5WorkerManagerError(
                    f"Unable to start MT5 worker for account "
                    f"{account.id}: {exc}"
                ) from exc

            self._workers[account.id] = worker
            mt5_runtime_manager.mark_running(account.id)

            return status

    def status_for_account(
        self,
        mt5_account_id: int,
        user_id: int,
    ) -> dict[str, Any]:
        with self._lock:
            try:
                runtime = (
                    mt5_runtime_manager.get_runtime_for_user(
                        mt5_account_id,
                        user_id,
                    )
                )
            except MT5RuntimeManagerError as exc:
                raise MT5WorkerManagerError(
                    str(exc)
                ) from exc

            worker = self._workers.get(mt5_account_id)

            if worker is None:
                return {
                    "running": False,
                    "mt5_account_id": runtime.mt5_account_id,
                    "user_id": runtime.user_id,
                    "login": runtime.login,
                    "server": runtime.server,
                    "connected": False,
                    "terminal_running": False,
                }

            try:
                status = worker.status()
            except MT5WorkerProcessError as exc:
                raise MT5WorkerManagerError(
                    f"Unable to read MT5 worker status for account "
                    f"{mt5_account_id}: {exc}"
                ) from exc

            if not status.get("running", False):
                mt5_runtime_manager.mark_stopped(
                    mt5_account_id
                )

            return status

    def get_positions(
        self,
        mt5_account_id: int,
        user_id: int,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return positions from one user's isolated MT5 worker.

        The MT5 API itself is accessed only inside the account worker
        process. The parent process never calls MetaTrader5 directly.
        """

        with self._lock:
            try:
                mt5_runtime_manager.get_runtime_for_user(
                    mt5_account_id,
                    user_id,
                )
            except MT5RuntimeManagerError as exc:
                raise MT5WorkerManagerError(
                    str(exc)
                ) from exc

            worker = self._workers.get(mt5_account_id)

            if worker is None:
                raise MT5WorkerManagerError(
                    f"MT5 worker for account "
                    f"{mt5_account_id} is not running."
                )

            if not worker.is_running():
                mt5_runtime_manager.mark_stopped(
                    mt5_account_id
                )

                raise MT5WorkerManagerError(
                    f"MT5 worker for account "
                    f"{mt5_account_id} is not running."
                )

            try:
                return worker.get_positions(symbol)
            except MT5WorkerProcessError as exc:
                raise MT5WorkerManagerError(
                    f"Unable to read MT5 positions for account "
                    f"{mt5_account_id}: {exc}"
                ) from exc

    def get_position(
        self,
        mt5_account_id: int,
        user_id: int,
        ticket: int,
    ) -> dict[str, Any] | None:
        """
        Return one position from the user's isolated MT5 worker.
        """

        with self._lock:
            try:
                mt5_runtime_manager.get_runtime_for_user(
                    mt5_account_id,
                    user_id,
                )
            except MT5RuntimeManagerError as exc:
                raise MT5WorkerManagerError(
                    str(exc)
                ) from exc

            worker = self._workers.get(mt5_account_id)

            if worker is None or not worker.is_running():
                mt5_runtime_manager.mark_stopped(
                    mt5_account_id
                )

                raise MT5WorkerManagerError(
                    f"MT5 worker for account "
                    f"{mt5_account_id} is not running."
                )

            try:
                return worker.get_position(ticket)
            except MT5WorkerProcessError as exc:
                raise MT5WorkerManagerError(
                    f"Unable to read MT5 position for account "
                    f"{mt5_account_id}: {exc}"
                ) from exc

    def get_position_summary(
        self,
        mt5_account_id: int,
        user_id: int,
    ) -> dict[str, Any]:
        """
        Return a summary from the user's isolated MT5 worker.
        """

        with self._lock:
            try:
                mt5_runtime_manager.get_runtime_for_user(
                    mt5_account_id,
                    user_id,
                )
            except MT5RuntimeManagerError as exc:
                raise MT5WorkerManagerError(
                    str(exc)
                ) from exc

            worker = self._workers.get(mt5_account_id)

            if worker is None or not worker.is_running():
                mt5_runtime_manager.mark_stopped(
                    mt5_account_id
                )

                raise MT5WorkerManagerError(
                    f"MT5 worker for account "
                    f"{mt5_account_id} is not running."
                )

            try:
                return worker.get_position_summary()
            except MT5WorkerProcessError as exc:
                raise MT5WorkerManagerError(
                    f"Unable to read MT5 position summary for account "
                    f"{mt5_account_id}: {exc}"
                ) from exc

    def stop_account(
        self,
        mt5_account_id: int,
        user_id: int,
    ) -> None:
        with self._lock:
            try:
                runtime = (
                    mt5_runtime_manager.get_runtime_for_user(
                        mt5_account_id,
                        user_id,
                    )
                )
            except MT5RuntimeManagerError as exc:
                raise MT5WorkerManagerError(
                    str(exc)
                ) from exc

            worker = self._workers.get(mt5_account_id)

            if worker is None:
                mt5_runtime_manager.mark_stopped(
                    mt5_account_id
                )
                return

            try:
                worker.stop()
            except MT5WorkerProcessError as exc:
                raise MT5WorkerManagerError(
                    f"Unable to stop MT5 worker for account "
                    f"{mt5_account_id}: {exc}"
                ) from exc
            finally:
                self._workers.pop(
                    mt5_account_id,
                    None,
                )
                mt5_runtime_manager.mark_stopped(
                    mt5_account_id
                )

            if runtime.mt5_account_id != mt5_account_id:
                raise MT5WorkerManagerError(
                    "MT5 runtime identity changed unexpectedly."
                )

    def is_running(
        self,
        mt5_account_id: int,
        user_id: int,
    ) -> bool:
        status = self.status_for_account(
            mt5_account_id,
            user_id,
        )

        return bool(status.get("running"))

    def registered_accounts(self) -> list[int]:
        with self._lock:
            return list(self._workers.keys())

    def shutdown_all(self) -> None:
        with self._lock:
            account_ids = list(self._workers.keys())

            for account_id in account_ids:
                worker = self._workers.pop(account_id)

                try:
                    worker.stop()
                finally:
                    mt5_runtime_manager.mark_stopped(
                        account_id
                    )


mt5_worker_manager = MT5WorkerManager()
