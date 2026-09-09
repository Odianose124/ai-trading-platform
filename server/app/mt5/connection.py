import logging
from typing import Any

import MetaTrader5 as mt5

logger = logging.getLogger(__name__)


class MT5ConnectionError(RuntimeError):
    """Raised when the MetaTrader 5 terminal cannot be accessed."""


class MT5Connection:
    def __init__(self) -> None:
        self._connected = False

    def connect(self) -> dict[str, Any]:
        if self._connected:
            try:
                return self.get_status()
            except MT5ConnectionError:
                self._connected = False

        if not mt5.initialize():
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
                f"Unable to read MT5 terminal information: "
                f"{mt5.last_error()}"
            )

        if account_info is None:
            mt5.shutdown()
            self._connected = False

            raise MT5ConnectionError(
                f"Unable to read MT5 account information: "
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

    def disconnect(self) -> None:
        if self._connected:
            mt5.shutdown()
            self._connected = False

            logger.info("Disconnected from MetaTrader 5")

    def is_connected(self) -> bool:
        """
        Verify the real MT5 connection instead of relying only
        on the process-local _connected flag.

        This allows the API to recover after Uvicorn reloads,
        worker restarts, or an MT5 terminal reconnection.
        """

        if self._connected:
            terminal_info = mt5.terminal_info()
            account_info = mt5.account_info()

            if terminal_info is not None and account_info is not None:
                return True

            self._connected = False

        try:
            if not mt5.initialize():
                return False

            terminal_info = mt5.terminal_info()
            account_info = mt5.account_info()

            if terminal_info is None or account_info is None:
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

    def get_status(
        self,
        terminal_info=None,
        account_info=None,
        version=None,
    ) -> dict[str, Any]:

        if not self._connected:
            raise MT5ConnectionError(
                "MetaTrader 5 is not connected"
            )

        terminal_info = terminal_info or mt5.terminal_info()
        account_info = account_info or mt5.account_info()
        version = version or mt5.version()

        if terminal_info is None or account_info is None:
            self._connected = False

            raise MT5ConnectionError(
                f"Unable to read MT5 status: {mt5.last_error()}"
            )

        return {
            "connected": True,
            "terminal": {
                "name": terminal_info.name,
                "company": terminal_info.company,
                "path": terminal_info.path,
            },
            "version": {
                "terminal": version[0] if version else None,
                "build": version[1] if version else None,
                "release_date": version[2] if version else None,
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
            },
        }


mt5_connection = MT5Connection()