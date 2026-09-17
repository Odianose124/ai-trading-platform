from dataclasses import dataclass
from threading import RLock

from app.models.mt5_trading_account import MT5TradingAccount
from app.mt5.runtime import (
    MT5AccountRuntime,
    MT5RuntimeConfigurationError,
)


class MT5RuntimeManagerError(RuntimeError):
    """Raised when an account-scoped MT5 runtime cannot be managed safely."""


@dataclass
class MT5RuntimeState:
    """
    Lifecycle state for one isolated MT5 account runtime.

    The manager tracks runtime ownership and lifecycle only. It does not
    create an MT5 connection and does not store account passwords.
    """

    runtime: MT5AccountRuntime
    running: bool = False


class MT5RuntimeManager:
    """
    Manages isolated MT5 runtime identities by registered account.

    One runtime belongs to exactly one MT5TradingAccount. The manager never
    shares runtime state between account IDs and never owns the MetaTrader 5
    Python connection itself.
    """

    def __init__(self) -> None:
        self._states: dict[int, MT5RuntimeState] = {}
        self._lock = RLock()

    def register_account(
        self,
        account: MT5TradingAccount,
    ) -> MT5AccountRuntime:
        runtime = MT5AccountRuntime.from_account(account)

        with self._lock:
            existing = self._states.get(runtime.mt5_account_id)

            if existing is not None:
                if existing.runtime.identity() != runtime.identity():
                    raise MT5RuntimeManagerError(
                        "The registered MT5 runtime identity does not match "
                        "the existing runtime state."
                    )

                return existing.runtime

            self._states[runtime.mt5_account_id] = MT5RuntimeState(
                runtime=runtime,
            )

        return runtime

    def get_runtime(
        self,
        mt5_account_id: int,
    ) -> MT5AccountRuntime:
        with self._lock:
            state = self._states.get(mt5_account_id)

            if state is None:
                raise MT5RuntimeManagerError(
                    f"No MT5 runtime is registered for account "
                    f"{mt5_account_id}."
                )

            return state.runtime

    def get_runtime_for_user(
        self,
        mt5_account_id: int,
        user_id: int,
    ) -> MT5AccountRuntime:
        runtime = self.get_runtime(mt5_account_id)

        if runtime.user_id != user_id:
            raise MT5RuntimeManagerError(
                "The MT5 runtime does not belong to the requested user."
            )

        return runtime

    def mark_running(
        self,
        mt5_account_id: int,
    ) -> MT5AccountRuntime:
        with self._lock:
            state = self._states.get(mt5_account_id)

            if state is None:
                raise MT5RuntimeManagerError(
                    f"No MT5 runtime is registered for account "
                    f"{mt5_account_id}."
                )

            state.running = True
            return state.runtime

    def mark_stopped(
        self,
        mt5_account_id: int,
    ) -> MT5AccountRuntime:
        with self._lock:
            state = self._states.get(mt5_account_id)

            if state is None:
                raise MT5RuntimeManagerError(
                    f"No MT5 runtime is registered for account "
                    f"{mt5_account_id}."
                )

            state.running = False
            return state.runtime

    def is_running(
        self,
        mt5_account_id: int,
    ) -> bool:
        with self._lock:
            state = self._states.get(mt5_account_id)
            return state.running if state is not None else False

    def unregister_account(
        self,
        mt5_account_id: int,
    ) -> None:
        with self._lock:
            state = self._states.get(mt5_account_id)

            if state is None:
                return

            if state.running:
                raise MT5RuntimeManagerError(
                    "A running MT5 runtime cannot be unregistered."
                )

            del self._states[mt5_account_id]

    def validate_runtime(
        self,
        mt5_account_id: int,
    ) -> MT5AccountRuntime:
        runtime = self.get_runtime(mt5_account_id)

        try:
            runtime.validate()
        except MT5RuntimeConfigurationError:
            raise

        return runtime

    def identities(self) -> list[dict[str, int | str]]:
        with self._lock:
            return [
                state.runtime.identity()
                for state in self._states.values()
            ]


mt5_runtime_manager = MT5RuntimeManager()
