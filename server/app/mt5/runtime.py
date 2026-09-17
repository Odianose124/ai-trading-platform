from dataclasses import dataclass
from pathlib import Path

from app.models.mt5_trading_account import MT5TradingAccount
from config.settings import settings


class MT5RuntimeConfigurationError(RuntimeError):
    """Raised when an MT5 account runtime cannot be configured safely."""


@dataclass(frozen=True)
class MT5AccountRuntime:
    """
    Immutable runtime identity for one registered MT5 trading account.

    This object does not hold an MT5 connection and does not hold a
    password. The actual MetaTrader 5 connection will be owned by the
    dedicated account worker.
    """

    mt5_account_id: int
    user_id: int
    login: int
    server: str
    runtime_directory: Path
    terminal_path: Path

    @classmethod
    def from_account(
        cls,
        account: MT5TradingAccount,
    ) -> "MT5AccountRuntime":
        if account.id is None:
            raise MT5RuntimeConfigurationError(
                "MT5 trading account must have a database ID."
            )

        if account.user_id is None:
            raise MT5RuntimeConfigurationError(
                "MT5 trading account must belong to a user."
            )

        if account.mt5_login <= 0:
            raise MT5RuntimeConfigurationError(
                "MT5 trading account login must be greater than zero."
            )

        server = account.server.strip()

        if not server:
            raise MT5RuntimeConfigurationError(
                "MT5 trading account server cannot be empty."
            )

        if not settings.MT5_RUNTIME_ROOT:
            raise MT5RuntimeConfigurationError(
                "MT5_RUNTIME_ROOT is not configured."
            )

        runtime_root = (
            Path(settings.MT5_RUNTIME_ROOT)
            .expanduser()
            .resolve()
        )

        runtime_directory = runtime_root / str(account.id)

        terminal_path = (
            runtime_directory
            / settings.MT5_TERMINAL_EXECUTABLE
        )

        return cls(
            mt5_account_id=account.id,
            user_id=account.user_id,
            login=int(account.mt5_login),
            server=server,
            runtime_directory=runtime_directory,
            terminal_path=terminal_path,
        )

    def validate(self) -> None:
        """
        Validate that the account runtime has been provisioned.

        This method deliberately does not create directories or copy
        terminal files. Provisioning belongs to the runtime manager.
        """

        if not self.runtime_directory.exists():
            raise MT5RuntimeConfigurationError(
                "The MT5 runtime directory does not exist: "
                f"{self.runtime_directory}"
            )

        if not self.runtime_directory.is_dir():
            raise MT5RuntimeConfigurationError(
                "The MT5 runtime path is not a directory: "
                f"{self.runtime_directory}"
            )

        if not self.terminal_path.exists():
            raise MT5RuntimeConfigurationError(
                "The MT5 terminal executable does not exist: "
                f"{self.terminal_path}"
            )

        if not self.terminal_path.is_file():
            raise MT5RuntimeConfigurationError(
                "The MT5 terminal path is not a file: "
                f"{self.terminal_path}"
            )

    def identity(self) -> dict[str, int | str]:
        return {
            "mt5_account_id": self.mt5_account_id,
            "user_id": self.user_id,
            "login": self.login,
            "server": self.server,
        }

