from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import MetaTrader5 as mt5


class MT5MarketDataError(RuntimeError):
    """Raised when MT5 market data cannot be retrieved."""


class MT5MarketDataService:
    """
    Production-safe MT5 market-data service.

    Responsibilities:
    - Ensure MT5 is initialized.
    - Resolve broker-specific symbols such as BTCUSD -> BTCUSDm.
    - Validate symbol information before using it.
    - Select symbols in Market Watch.
    - Retrieve live bid/ask prices safely.
    - Retrieve symbol trading specifications safely.
    - Automatically rediscover stale broker mappings.
    """

    def __init__(self) -> None:
        self._supported_symbols: dict[str, str] = {
            "XAUUSD": "XAUUSDm",
            "BTCUSD": "BTCUSDm",
            "EURUSD": "EURUSDm",
            "GBPUSD": "GBPUSDm",
            "USDJPY": "",
            "USDCHF": "",
            "AUDUSD": "",
            "USDCAD": "",
            "NZDUSD": "",
            "EURGBP": "",
            "EURJPY": "",
            "GBPJPY": "",
            "AUDJPY": "",
            "XAGUSD": "",
        }

    def _ensure_mt5_initialized(self) -> None:
        """
        Ensure the MetaTrader 5 terminal is initialized.

        The Python MT5 package returns None for many operations when
        the terminal is not initialized, so this check prevents
        NoneType errors from leaking into the application.
        """

        try:
            terminal_info = mt5.terminal_info()

            if terminal_info is not None:
                return

        except Exception:
            pass

        initialized = mt5.initialize()

        if not initialized:
            raise MT5MarketDataError(
                f"Unable to initialize MetaTrader 5: {mt5.last_error()}"
            )

        terminal_info = mt5.terminal_info()

        if terminal_info is None:
            raise MT5MarketDataError(
                "MetaTrader 5 initialized but terminal information "
                f"is unavailable: {mt5.last_error()}"
            )

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        if not isinstance(symbol, str):
            raise MT5MarketDataError(
                "Trading symbol must be a string"
            )

        normalized_symbol = symbol.strip().upper()

        if not normalized_symbol:
            raise MT5MarketDataError(
                "Trading symbol cannot be empty"
            )

        return normalized_symbol

    def _get_symbol_info_safe(self, mt5_symbol: str):
        """
        Safely retrieve symbol information.

        Never allows a None symbol-info object to propagate.
        """

        self._ensure_mt5_initialized()

        if not mt5_symbol:
            raise MT5MarketDataError(
                "MT5 broker symbol cannot be empty"
            )

        symbol_info = mt5.symbol_info(mt5_symbol)

        if symbol_info is None:
            raise MT5MarketDataError(
                f"MT5 symbol information is unavailable for "
                f"{mt5_symbol}: {mt5.last_error()}"
            )

        return symbol_info

    def _select_symbol(self, mt5_symbol: str):
        """
        Select the broker symbol in Market Watch and return
        freshly validated symbol information.
        """

        self._ensure_mt5_initialized()

        symbol_info = self._get_symbol_info_safe(mt5_symbol)

        selected = mt5.symbol_select(mt5_symbol, True)

        if not selected:
            raise MT5MarketDataError(
                f"Unable to select MT5 symbol {mt5_symbol}: "
                f"{mt5.last_error()}"
            )

        # Refresh symbol information after selection.
        symbol_info = mt5.symbol_info(mt5_symbol)

        if symbol_info is None:
            raise MT5MarketDataError(
                f"MT5 symbol {mt5_symbol} became unavailable after "
                f"selection: {mt5.last_error()}"
            )

        return symbol_info

    def _discover_from_available_symbols(
        self,
        normalized_symbol: str,
    ) -> str:
        """
        Discover a broker-specific symbol.

        Examples:
            BTCUSD -> BTCUSDm
            XAUUSD -> XAUUSDm
            EURUSD -> EURUSDm

        The resolver supports exact symbols, suffixes and prefixes
        without hard-coding one broker's naming convention.
        """

        self._ensure_mt5_initialized()

        symbols = mt5.symbols_get()

        if symbols is None:
            raise MT5MarketDataError(
                "Unable to retrieve MT5 symbol list: "
                f"{mt5.last_error()}"
            )

        exact_candidates: list[str] = []
        suffix_candidates: list[str] = []
        prefix_candidates: list[str] = []

        for item in symbols:
            if item is None:
                continue

            broker_symbol = getattr(item, "name", None)

            if not isinstance(broker_symbol, str):
                continue

            broker_symbol = broker_symbol.strip()

            if not broker_symbol:
                continue

            broker_symbol_upper = broker_symbol.upper()

            if broker_symbol_upper == normalized_symbol:
                exact_candidates.append(broker_symbol)
                continue

            if broker_symbol_upper.startswith(normalized_symbol):
                suffix_candidates.append(broker_symbol)
                continue

            if broker_symbol_upper.endswith(normalized_symbol):
                prefix_candidates.append(broker_symbol)

        if exact_candidates:
            exact_candidates.sort(key=len)
            return exact_candidates[0]

        if suffix_candidates:
            suffix_candidates.sort(
                key=lambda value: (
                    len(value) - len(normalized_symbol),
                    len(value),
                )
            )
            return suffix_candidates[0]

        if prefix_candidates:
            prefix_candidates.sort(
                key=lambda value: (
                    len(value) - len(normalized_symbol),
                    len(value),
                )
            )
            return prefix_candidates[0]

        raise MT5MarketDataError(
            f"MT5 broker symbol could not be discovered for "
            f"{normalized_symbol}"
        )

    def discover_symbol(self, symbol: str) -> str:
        """
        Resolve an application symbol to the actual MT5 broker symbol.
        """

        normalized_symbol = self._normalize_symbol(symbol)

        self._ensure_mt5_initialized()

        # ---------------------------------------------------------
        # 1. Try existing broker mapping.
        # ---------------------------------------------------------

        mapped_symbol = self._supported_symbols.get(normalized_symbol)

        if mapped_symbol:
            try:
                self._select_symbol(mapped_symbol)

                return mapped_symbol

            except MT5MarketDataError:
                # Mapping may be stale or broker configuration may
                # have changed. Rediscover instead of failing.
                self._supported_symbols.pop(
                    normalized_symbol,
                    None,
                )

        # ---------------------------------------------------------
        # 2. Try exact symbol.
        # ---------------------------------------------------------

        try:
            self._select_symbol(normalized_symbol)

            self._supported_symbols[normalized_symbol] = (
                normalized_symbol
            )

            return normalized_symbol

        except MT5MarketDataError:
            pass

        # ---------------------------------------------------------
        # 3. Discover broker-specific symbol.
        # ---------------------------------------------------------

        discovered_symbol = (
            self._discover_from_available_symbols(
                normalized_symbol
            )
        )

        # ---------------------------------------------------------
        # 4. Validate discovered symbol before saving mapping.
        # ---------------------------------------------------------

        try:
            self._select_symbol(discovered_symbol)

        except MT5MarketDataError as exc:
            raise MT5MarketDataError(
                f"MT5 discovered symbol {discovered_symbol} for "
                f"{normalized_symbol}, but the symbol could not be "
                f"selected or validated: {exc}"
            ) from exc

        self._supported_symbols[normalized_symbol] = discovered_symbol

        return discovered_symbol

    def _get_mt5_symbol(self, symbol: str) -> str:
        return self.discover_symbol(symbol)

    def get_tick(self, symbol: str) -> dict[str, Any]:
        """
        Retrieve a validated live MT5 tick.
        """

        normalized_symbol = self._normalize_symbol(symbol)

        mt5_symbol = self._get_mt5_symbol(normalized_symbol)

        # Validate/select the symbol again immediately before
        # requesting live market data.
        self._select_symbol(mt5_symbol)

        tick = mt5.symbol_info_tick(mt5_symbol)

        if tick is None:
            # The broker mapping may have become stale.
            #
            # Clear it and attempt one controlled rediscovery.
            self._supported_symbols.pop(
                normalized_symbol,
                None,
            )

            mt5_symbol = self.discover_symbol(
                normalized_symbol
            )

            tick = mt5.symbol_info_tick(mt5_symbol)

        if tick is None:
            raise MT5MarketDataError(
                f"Unable to retrieve live tick for "
                f"{mt5_symbol}: {mt5.last_error()}"
            )

        bid_value = getattr(tick, "bid", None)
        ask_value = getattr(tick, "ask", None)
        timestamp_value = getattr(tick, "time", None)

        if bid_value is None:
            raise MT5MarketDataError(
                f"MT5 returned no bid price for {mt5_symbol}"
            )

        if ask_value is None:
            raise MT5MarketDataError(
                f"MT5 returned no ask price for {mt5_symbol}"
            )

        if timestamp_value is None:
            raise MT5MarketDataError(
                f"MT5 returned no timestamp for {mt5_symbol}"
            )

        bid = Decimal(str(bid_value))
        ask = Decimal(str(ask_value))

        if bid <= 0:
            raise MT5MarketDataError(
                f"MT5 returned an invalid bid price for "
                f"{mt5_symbol}: {bid}"
            )

        if ask <= 0:
            raise MT5MarketDataError(
                f"MT5 returned an invalid ask price for "
                f"{mt5_symbol}: {ask}"
            )

        if ask < bid:
            raise MT5MarketDataError(
                f"MT5 returned invalid market geometry for "
                f"{mt5_symbol}: ask {ask} < bid {bid}"
            )

        spread = ask - bid

        return {
            "symbol": normalized_symbol,
            "mt5_symbol": mt5_symbol,
            "bid": bid,
            "ask": ask,
            "spread": spread,
            "timestamp": datetime.fromtimestamp(
                int(timestamp_value),
                tz=timezone.utc,
            ),
            "source": "MetaTrader 5",
        }

    def get_symbol_info(self, symbol: str) -> dict[str, Any]:
        """
        Retrieve validated broker trading specifications.
        """

        normalized_symbol = self._normalize_symbol(symbol)

        mt5_symbol = self._get_mt5_symbol(normalized_symbol)

        symbol_info = self._select_symbol(mt5_symbol)

        digits = getattr(symbol_info, "digits", None)
        point = getattr(symbol_info, "point", None)
        contract_size = getattr(
            symbol_info,
            "trade_contract_size",
            None,
        )

        volume_min = getattr(
            symbol_info,
            "volume_min",
            None,
        )

        volume_max = getattr(
            symbol_info,
            "volume_max",
            None,
        )

        volume_step = getattr(
            symbol_info,
            "volume_step",
            None,
        )

        tick_size = getattr(
            symbol_info,
            "trade_tick_size",
            None,
        )

        tick_value = getattr(
            symbol_info,
            "trade_tick_value",
            None,
        )

        if digits is None:
            raise MT5MarketDataError(
                f"MT5 returned no price precision for "
                f"{mt5_symbol}"
            )

        if point is None:
            raise MT5MarketDataError(
                f"MT5 returned no point size for "
                f"{mt5_symbol}"
            )

        if contract_size is None:
            raise MT5MarketDataError(
                f"MT5 returned no contract size for "
                f"{mt5_symbol}"
            )

        if volume_min is None:
            raise MT5MarketDataError(
                f"MT5 returned no minimum volume for "
                f"{mt5_symbol}"
            )

        if volume_max is None:
            raise MT5MarketDataError(
                f"MT5 returned no maximum volume for "
                f"{mt5_symbol}"
            )

        if volume_step is None:
            raise MT5MarketDataError(
                f"MT5 returned no volume step for "
                f"{mt5_symbol}"
            )

        if tick_size is None:
            raise MT5MarketDataError(
                f"MT5 returned no tick size for "
                f"{mt5_symbol}"
            )

        if tick_value is None:
            raise MT5MarketDataError(
                f"MT5 returned no tick value for "
                f"{mt5_symbol}"
            )

        return {
            "symbol": normalized_symbol,
            "mt5_symbol": mt5_symbol,
            "description": getattr(
                symbol_info,
                "description",
                "",
            ),
            "currency_base": getattr(
                symbol_info,
                "currency_base",
                "",
            ),
            "currency_profit": getattr(
                symbol_info,
                "currency_profit",
                "",
            ),
            "currency_margin": getattr(
                symbol_info,
                "currency_margin",
                "",
            ),
            "digits": int(digits),
            "point": Decimal(str(point)),
            "trade_contract_size": Decimal(
                str(contract_size)
            ),
            "volume_min": Decimal(str(volume_min)),
            "volume_max": Decimal(str(volume_max)),
            "volume_step": Decimal(str(volume_step)),
            "trade_tick_size": Decimal(
                str(tick_size)
            ),
            "trade_tick_value": Decimal(
                str(tick_value)
            ),
            "source": "MetaTrader 5",
        }

    def get_supported_symbols(self) -> dict[str, str]:
        return self._supported_symbols.copy()


mt5_market_data_service = MT5MarketDataService()