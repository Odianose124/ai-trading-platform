from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from app.models.mt5_trading_account import MT5TradingAccount
from app.mt5.runtime import (
    MT5AccountRuntime,
    MT5RuntimeConfigurationError,
)
from config.settings import settings


class MT5RuntimeManagerError(RuntimeError):
    """Raised when an account-scoped MT5 runtime cannot be managed safely."""


@dataclass
class MT5RuntimeState:
    """
    Lifecycle state for one isolated MT5 account runtime.

    Each database MT5 account owns exactly one runtime directory.
    """

    runtime: MT5AccountRuntime
    running: bool = False


class MT5RuntimeManager:
    """
    Provisions and manages isolated MT5 runtimes.

    Runtime ownership is strictly account-scoped:

        MT5 account 1 -> runtime 1
        MT5 account 2 -> runtime 2
        MT5 account 3 -> runtime 3

    The manager never stores MT5 passwords and never owns the MT5
    Python connection.
    """

    def __init__(self) -> None:
        self._states: dict[int, MT5RuntimeState] = {}
        self._lock = RLock()

    # ------------------------------------------------------------------
    # RUNTIME PROVISIONING
    # ------------------------------------------------------------------

    def provision_account(
        self,
        account: MT5TradingAccount,
    ) -> MT5AccountRuntime:
        """
        Automatically provision the isolated runtime for one account.

        Each MT5 database account receives its own portable runtime
        directory.

        Existing runtimes are preserved. The common MT5 installation
        is copied only when the account runtime has not yet been
        provisioned.

        The user's MetaQuotes data directory is never copied.
        """

        runtime = MT5AccountRuntime.from_account(account)

        install_root_value = settings.MT5_INSTALL_ROOT

        if not install_root_value:
            raise MT5RuntimeConfigurationError(
                "MT5_INSTALL_ROOT is not configured."
            )

        install_root = (
            Path(install_root_value)
            .expanduser()
            .resolve()
        )

        if not install_root.exists():
            raise MT5RuntimeConfigurationError(
                "The MT5 installation directory does not exist: "
                f"{install_root}"
            )

        if not install_root.is_dir():
            raise MT5RuntimeConfigurationError(
                "The MT5 installation path is not a directory: "
                f"{install_root}"
            )

        source_terminal = (
            install_root
            / settings.MT5_TERMINAL_EXECUTABLE
        )

        if not source_terminal.exists():
            raise MT5RuntimeConfigurationError(
                "The MT5 terminal executable does not exist in the "
                "configured installation: "
                f"{source_terminal}"
            )

        if not source_terminal.is_file():
            raise MT5RuntimeConfigurationError(
                "The configured MT5 terminal executable is not a file: "
                f"{source_terminal}"
            )

        runtime.runtime_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        # If this account runtime already contains its terminal,
        # preserve the existing isolated runtime and do not overwrite
        # account-specific portable data.
        if runtime.terminal_path.is_file():
            runtime.validate()
            return runtime

        # First-time provisioning only.
        #
        # Copy the common Program Files installation into this
        # account's private portable runtime.
        #
        # We intentionally do NOT copy:
        # C:\Users\<user>\AppData\Roaming\MetaQuotes\Terminal
        #
        # because that directory can contain credentials/session state
        # belonging to another MT5 account.
        for source in install_root.iterdir():
            destination = runtime.runtime_directory / source.name

            if source.is_dir():
                shutil.copytree(
                    source,
                    destination,
                    dirs_exist_ok=True,
                )
            elif source.is_file():
                shutil.copy2(
                    source,
                    destination,
                )

        runtime.validate()

        return runtime

    # ------------------------------------------------------------------
    # REGISTRATION
    # ------------------------------------------------------------------

    def register_account(
        self,
        account: MT5TradingAccount,
    ) -> MT5AccountRuntime:
        runtime = self.provision_account(account)

        with self._lock:
            existing = self._states.get(
                runtime.mt5_account_id
            )

            if existing is not None:
                if existing.runtime.identity() != runtime.identity():
                    raise MT5RuntimeManagerError(
                        "The registered MT5 runtime identity does not "
                        "match the existing runtime state."
                    )

                return existing.runtime

            self._states[runtime.mt5_account_id] = MT5RuntimeState(
                runtime=runtime,
            )

        return runtime

    # ------------------------------------------------------------------
    # LOOKUP
    # ------------------------------------------------------------------

    def get_runtime(
        self,
        mt5_account_id: int,
    ) -> MT5AccountRuntime:
        with self._lock:
            state = self._states.get(
                mt5_account_id
            )

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
        runtime = self.get_runtime(
            mt5_account_id
        )

        if runtime.user_id != user_id:
            raise MT5RuntimeManagerError(
                "The MT5 runtime does not belong to the requested user."
            )

        return runtime

    # ------------------------------------------------------------------
    # LIFECYCLE
    # ------------------------------------------------------------------

    def mark_running(
        self,
        mt5_account_id: int,
    ) -> MT5AccountRuntime:
        with self._lock:
            state = self._states.get(
                mt5_account_id
            )

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
            state = self._states.get(
                mt5_account_id
            )

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
            state = self._states.get(
                mt5_account_id
            )

            return (
                state.running
                if state is not None
                else False
            )

    def unregister_account(
        self,
        mt5_account_id: int,
    ) -> None:
        with self._lock:
            state = self._states.get(
                mt5_account_id
            )

            if state is None:
                return

            if state.running:
                raise MT5RuntimeManagerError(
                    "A running MT5 runtime cannot be unregistered."
                )

            del self._states[
                mt5_account_id
            ]

    # ------------------------------------------------------------------
    # VALIDATION
    # ------------------------------------------------------------------

    def validate_runtime(
        self,
        mt5_account_id: int,
    ) -> MT5AccountRuntime:
        runtime = self.get_runtime(
            mt5_account_id
        )

        runtime.validate()

        return runtime

    # ------------------------------------------------------------------
    # INFORMATION
    # ------------------------------------------------------------------

    def identities(
        self,
    ) -> list[dict[str, int | str]]:
        with self._lock:
            return [
                state.runtime.identity()
                for state in self._states.values()
            ]


mt5_runtime_manager = MT5RuntimeManager()
