import MetaTrader5 as mt5

from app.database.trade_history import TradeHistory


class MT5Executor:

    def __init__(self):
        self.connected = False
        self.trade_history = TradeHistory()

    # =====================================
    # CONNECT MT5
    # =====================================

    def connect(self):

        if not mt5.initialize():
            return {
                "status": "error",
                "message": "MT5 initialization failed",
                "error": str(mt5.last_error()),
            }

        account = mt5.account_info()

        if account is None:
            return {
                "status": "error",
                "message": "No MT5 account connected",
            }

        terminal = mt5.terminal_info()

        if terminal is None:
            return {
                "status": "error",
                "message": "Unable to read MT5 terminal",
            }

        if not terminal.trade_allowed:
            return {
                "status": "error",
                "message": "AutoTrading disabled",
            }

        self.connected = True

        return {
            "status": "connected",
            "login": account.login,
            "balance": account.balance,
            "currency": account.currency,
        }

    # =====================================

    def shutdown(self):

        mt5.shutdown()
        self.connected = False

    # =====================================
    # SYMBOL VALIDATION
    # =====================================

    def check_symbol(self, symbol):

        info = mt5.symbol_info(symbol)

        if info is None:
            return {
                "available": False,
                "message": f"{symbol} unavailable",
            }

        if not info.visible:

            if not mt5.symbol_select(symbol, True):
                return {
                    "available": False,
                    "message": f"Unable to activate {symbol}",
                }

        return {
            "available": True,
            "digits": info.digits,
            "point": info.point,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
        }

    # =====================================
    # GET FILLING MODE
    # =====================================

    def get_filling_mode(self, info):

        if info.filling_mode & mt5.ORDER_FILLING_IOC:
            return mt5.ORDER_FILLING_IOC

        if info.filling_mode & mt5.ORDER_FILLING_FOK:
            return mt5.ORDER_FILLING_FOK

        return mt5.ORDER_FILLING_RETURN

    # =====================================
    # NORMALIZE LOT SIZE
    # =====================================

    def normalize_volume(self, volume, info):

        step = info.volume_step

        volume = max(
            info.volume_min,
            min(
                volume,
                info.volume_max,
            ),
        )

        volume = round(
            volume / step
        ) * step

        return round(
            volume,
            2,
        )

    # =====================================
    # EXECUTE TRADE
    # =====================================

    def execute_trade(
        self,
        symbol,
        direction,
        volume,
        stop_loss,
        take_profit,
    ):

        if not self.connected:

            connection = self.connect()

            if connection["status"] != "connected":
                return connection

        symbol_check = self.check_symbol(symbol)

        if not symbol_check["available"]:
            return {
                "status": "error",
                "message": symbol_check["message"],
            }

        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)

        if tick is None:
            return {
                "status": "error",
                "message": "No live market price",
            }

        direction = direction.lower()

        # =====================================
        # DETERMINE ORDER TYPE
        # =====================================

        if direction in [
            "buy",
            "long",
        ]:

            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask

            # FINAL SAFETY CHECK

            if stop_loss >= price:
                return {
                    "status": "blocked",
                    "reason": "BUY invalidated",
                    "message": (
                        f"BUY SL {stop_loss} "
                        f"must be below entry {price}"
                    ),
                }

            if take_profit <= price:
                return {
                    "status": "blocked",
                    "reason": "BUY invalidated",
                    "message": (
                        f"BUY TP {take_profit} "
                        f"must be above entry {price}"
                    ),
                }

        elif direction in [
            "sell",
            "short",
        ]:

            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid

            if stop_loss <= price:
                return {
                    "status": "blocked",
                    "reason": "SELL invalidated",
                    "message": (
                        f"SELL SL {stop_loss} "
                        f"must be above entry {price}"
                    ),
                }

            if take_profit >= price:
                return {
                    "status": "blocked",
                    "reason": "SELL invalidated",
                    "message": (
                        f"SELL TP {take_profit} "
                        f"must be below entry {price}"
                    ),
                }

        else:

            return {
                "status": "error",
                "message": "Invalid direction",
            }

        # =====================================
        # NORMALIZE PRICES
        # =====================================

        digits = info.digits

        price = round(
            price,
            digits,
        )

        stop_loss = round(
            stop_loss,
            digits,
        )

        take_profit = round(
            take_profit,
            digits,
        )

        # =====================================
        # NORMALIZE VOLUME
        # =====================================

        volume = self.normalize_volume(
            float(volume),
            info,
        )

        # =====================================
        # FILLING MODE
        # =====================================

        filling = self.get_filling_mode(info)

        # =====================================
        # BUILD MT5 REQUEST
        # =====================================

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": stop_loss,
            "tp": take_profit,
            "deviation": 50,
            "magic": 202609,
            "comment": "AI Trading Platform",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }

        # =====================================
        # MT5 PRE-FLIGHT ORDER CHECK
        # =====================================

        check_result = mt5.order_check(request)

        if check_result is None:

            return {
                "status": "preflight_failed",
                "stage": "order_check",
                "message": "MT5 order_check returned no result",
                "error": str(mt5.last_error()),
                "request": request,
            }

        if check_result.retcode != 0:

            return {
                "status": "preflight_failed",
                "stage": "order_check",
                "retcode": check_result.retcode,
                "message": check_result.comment,
                "request": request,
            }

        # =====================================
        # SEND REAL MT5 ORDER
        # =====================================

        result = mt5.order_send(request)

        if result is None:

            return {
                "status": "error",
                "stage": "order_send",
                "message": "Order send failed",
                "error": str(mt5.last_error()),
            }

        if result.retcode != mt5.TRADE_RETCODE_DONE:

            return {
                "status": "failed",
                "stage": "order_send",
                "retcode": result.retcode,
                "message": result.comment,
                "request": request,
            }

        # =====================================
        # SAVE HISTORY
        # =====================================

        try:

            self.trade_history.save_trade(
                {
                    "ticket": result.order,
                    "deal": result.deal,
                    "symbol": symbol,
                    "direction": direction,
                    "volume": volume,
                    "entry_price": price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "strategy": "AI Trading Strategy",
                }
            )

        except Exception as e:

            print(
                "History save failed:",
                e,
            )

        # =====================================
        # FINAL RESPONSE
        # =====================================

        return {
            "status": "executed",
            "ticket": result.order,
            "deal": result.deal,
            "symbol": symbol,
            "direction": direction,
            "volume": volume,
            "entry_price": price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "preflight": {
                "retcode": check_result.retcode,
                "message": check_result.comment,
            },
            "market": {
                "bid": tick.bid,
                "ask": tick.ask,
                "spread": round(
                    tick.ask - tick.bid,
                    digits,
                ),
            },
        }