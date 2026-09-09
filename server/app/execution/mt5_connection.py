import MetaTrader5 as mt5


class MT5Connection:

    def connect(self):

        if not mt5.initialize():
            return {
                "connected": False,
                "error": mt5.last_error()
            }


        account = mt5.account_info()


        if account is None:
            return {
                "connected": False,
                "error": "No MT5 account detected"
            }


        return {
            "connected": True,
            "login": account.login,
            "server": account.server,
            "balance": account.balance
        }



    def disconnect(self):

        mt5.shutdown()