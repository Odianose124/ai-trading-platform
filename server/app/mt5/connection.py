import logging
from typing import Any

import MetaTrader5 as mt5

logger = logging.getLogger(__name__)


class MT5ConnectionError(RuntimeError):
    """Raised when MetaTrader 5 cannot be accessed safely."""


class MT5AccountMismatchError(MT5ConnectionError):
    """Raised when the connected MT5 account does not belong to the user."""


class MT5Connection:
    """
    Authoritative process-level MT5 connection.

    Important:
    - This class NEVER switches accounts automatically.
    - It only connects to the terminal account that is already active.
    - Callers must explicitly verify that the connected account matches
      the authenticated user's registered MT5TradingAccount.
    """

    def __init__(self) -> None:
        self._connected = False

    # ------------------------------------------------------------------
    # CONNECTION
    # ------------------------------------------------------------------

    def connect(self) -> dict[str, Any]:
        """
        Connect to the currently configured MT5 terminal/account.

        This intentionally does not call mt5.login().

        The application must never silently switch a user's MT5 account.
        """

        if self._connected:
            try:
                return self.get_status()
            except MT5ConnectionError:
                self._connected = False

        initialized = mt5.initialize()

        if not initialized:
            error = mt5.last_error()

            raise MT5ConnectionError(
                f"MetaTrader 5 initialization failed: {error}"
            )

        terminal_info = mt5.terminal_info()
        account_info = mt5.account_info()
        version = mt5.version()

        if terminal_info is None:
            mt5.shutdown()
            self._connected = False

            raise MT5ConnectionError(
                "Unable to read MetaTrader 5 terminal information: "
                f"{mt5.last_error()}"
            )

        if account_info is None:
            mt5.shutdown()
            self._connected = False

            raise MT5ConnectionError(
                "Unable to read MetaTrader 5 account information: "
                f"{mt5.last_error()}"
            )

        self._connected = True

        logger.info(
            "Connected to MetaTrader 5 | account=%s | server=%s",
            account_info.login,
            account_info.server,
        )

        return self.get_status(
            terminal_info=terminal_info,
            account_info=account_info,
            version=version,
        )

    # ------------------------------------------------------------------
    # ENSURE CONNECTION
    # ------------------------------------------------------------------

    def ensure_connected(self) -> dict[str, Any]:
        """
        Ensure that a live MT5 terminal/account connection exists.

        Unlike the previous implementation, this method never silently
        changes the trading account.
        """

        if self.is_connected():
            return self.get_status()

        return self.connect()

    # ------------------------------------------------------------------
    # ACCOUNT OWNERSHIP
    # ------------------------------------------------------------------

    def verify_account(
        self,
        expected_login: int,
        expected_server: str,
    ) -> dict[str, Any]:
        """
        Verify that the currently connected MT5 account exactly matches
        the account registered for the authenticated application user.
        """

        try:
            expected_login = int(expected_login)
        except (TypeError, ValueError) as exc:
            raise MT5AccountMismatchError(
                "Registered MT5 login is invalid."
            ) from exc

        expected_server = str(expected_server).strip()

        if not expected_server:
            raise MT5AccountMismatchError(
                "Registered MT5 server is missing."
            )

        self.ensure_connected()

        account_info = mt5.account_info()

        if account_info is None:
            self._connected = False

            raise MT5ConnectionError(
                "Unable to read the currently connected MT5 account: "
                f"{mt5.last_error()}"
            )

        actual_login = int(account_info.login)
        actual_server = str(account_info.server).strip()

        if actual_login != expected_login:
            raise MT5AccountMismatchError(
                "The connected MT5 account does not match the account "
                "registered for this user."
            )

        if actual_server.lower() != expected_server.lower():
            raise MT5AccountMismatchError(
                "The connected MT5 server does not match the server "
                "registered for this user."
            )

        return {
            "verified": True,
            "login": actual_login,
            "server": actual_server,
            "name": account_info.name,
            "currency": account_info.currency,
            "balance": account_info.balance,
            "equity": account_info.equity,
            "margin": account_info.margin,
            "free_margin": account_info.margin_free,
            "leverage": account_info.leverage,
            "trade_allowed": account_info.trade_allowed,
        }

    # ------------------------------------------------------------------
    # CONNECTION STATUS
    # ------------------------------------------------------------------

    def is_connected(self) -> bool:
        """
        Verify the real MT5 connection instead of relying only on the
        process-local flag.
        """

        if self._connected:
            terminal_info = mt5.terminal_info()
            account_info = mt5.account_info()

            if (
                terminal_info is not None
                and account_info is not None
            ):
                return True

            self._connected = False

        try:
            initialized = mt5.initialize()

            if not initialized:
                return False

            terminal_info = mt5.terminal_info()
            account_info = mt5.account_info()

            if (
                terminal_info is None
                or account_info is None
            ):
                self._connected = False
                return False

            self._connected = True

            logger.info(
                "MT5 connection recovered | account=%s | server=%s",
                account_info.login,
                account_info.server,
            )

            return True

        except Exception as exc:
            logger.warning(
                "Unable to verify/recover MT5 connection: %s",
                exc,
            )

            self._connected = False
            return False

    # ------------------------------------------------------------------
    # DISCONNECT
    # ------------------------------------------------------------------

    def disconnect(self) -> None:
        """
        Close the process-level MT5 terminal connection.
        """

        if self._connected:
            mt5.shutdown()
            self._connected = False

            logger.info("Disconnected from MetaTrader 5")

    # ------------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------------

    def get_status(
        self,
        terminal_info=None,
        account_info=None,
        version=None,
    ) -> dict[str, Any]:

        if not self._connected:
            raise MT5ConnectionError(
                "MetaTrader 5 is not connected."
            )

        terminal_info = (
            terminal_info
            or mt5.terminal_info()
        )

        account_info = (
            account_info
            or mt5.account_info()
        )

        version = (
            version
            or mt5.version()
        )

        if (
            terminal_info is None
            or account_info is None
        ):
            self._connected = False

            raise MT5ConnectionError(
                "Unable to read MT5 status: "
                f"{mt5.last_error()}"
            )

        return {
            "connected": True,
            "terminal": {
                "name": terminal_info.name,
                "company": terminal_info.company,
                "path": terminal_info.path,
            },
            "version": {
                "terminal": (
                    version[0]
                    if version
                    else None
                ),
                "build": (
                    version[1]
                    if version
                    else None
                ),
                "release_date": (
                    version[2]
                    if version
                    else None
                ),
            },
            "account": {
                "login": account_info.login,
                "server": account_info.server,
                "name": account_info.name,
                "currency": account_info.currency,
                "balance": account_info.balance,
                "equity": account_info.equity,
                "margin": account_info.margin,
                "free_margin": account_info.margin_free,
                "leverage": account_info.leverage,
                "trade_allowed": account_info.trade_allowed,
                "trade_expert": account_info.trade_expert,
            },
        }


mt5_connection = MT5Connection()