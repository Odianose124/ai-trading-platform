import MetaTrader5 as mt5



class LotCalculator:



    def __init__(self):

        self.connected = False






    # =====================================
    # CONNECT MT5
    # =====================================

    def connect(self):


        if not mt5.initialize():


            return False



        account = mt5.account_info()


        if account is None:


            return False



        self.connected = True


        return True







    # =====================================
    # SYMBOL CHECK
    # =====================================

    def get_symbol_info(self, symbol):


        info = mt5.symbol_info(symbol)



        if info is None:


            return None




        if not info.visible:


            if not mt5.symbol_select(
                symbol,
                True
            ):


                return None




        return info







    # =====================================
    # NORMALIZE LOT SIZE
    # =====================================

    def normalize_volume(
        self,
        volume,
        info
    ):


        volume = max(

            info.volume_min,

            min(

                volume,

                info.volume_max

            )

        )



        step = info.volume_step



        if step > 0:


            volume = round(

                volume / step

            ) * step





        return round(

            volume,

            2

        )









    # =====================================
    # CALCULATE LOT SIZE
    # =====================================

    def calculate(
        self,
        balance,
        risk_percent,
        entry_price,
        stop_loss,
        symbol="XAUUSDm"
    ):



        # ==============================
        # MT5 CONNECTION
        # ==============================


        if not self.connected:


            if not self.connect():


                return {


                    "status":"error",


                    "message":
                    "MT5 connection failed"

                }







        # ==============================
        # SYMBOL DATA
        # ==============================


        info = self.get_symbol_info(
            symbol
        )



        if info is None:


            return {


                "status":"error",


                "message":
                f"Symbol {symbol} unavailable"

            }







        # ==============================
        # PRICE VALIDATION
        # ==============================


        if entry_price <= 0:


            return {


                "status":"error",


                "message":
                "Invalid entry price"

            }




        if stop_loss <= 0:


            return {


                "status":"error",


                "message":
                "Invalid stop loss"

            }






        stop_distance = abs(

            entry_price -

            stop_loss

        )





        if stop_distance <= 0:


            return {


                "status":"error",


                "message":
                "Invalid stop distance"

            }







        # ==============================
        # RISK MONEY
        # ==============================


        risk_amount = (


            balance *

            (

                risk_percent /

                100

            )

        )







        if risk_amount <= 0:


            return {


                "status":"error",


                "message":
                "Invalid risk amount"

            }








        # ==============================
        # BROKER DATA
        # ==============================


        tick_size = info.trade_tick_size


        tick_value = info.trade_tick_value



        contract_size = info.trade_contract_size







        if tick_size <= 0:


            return {


                "status":"error",


                "message":
                "Invalid tick size"

            }





        if tick_value <= 0:


            return {


                "status":"error",


                "message":
                "Invalid tick value"

            }









        # ==============================
        # LOSS PER LOT
        # ==============================


        ticks = (

            stop_distance /

            tick_size

        )




        loss_per_lot = (

            ticks *

            tick_value

        )








        if loss_per_lot <= 0:


            return {


                "status":"error",


                "message":
                "Loss calculation failed"

            }







        # ==============================
        # LOT CALCULATION
        # ==============================


        lot_size = (


            risk_amount /

            loss_per_lot

        )








        lot_size = self.normalize_volume(

            lot_size,

            info

        )







        # ==============================
        # FINAL RESPONSE
        # ==============================


        return {



            "status":"calculated",



            "symbol":symbol,



            "balance":round(

                balance,

                2

            ),



            "risk_percent":risk_percent,



            "risk_amount":round(

                risk_amount,

                2

            ),



            "entry_price":entry_price,



            "stop_loss":stop_loss,



            "stop_distance":round(

                stop_distance,

                info.digits

            ),



            "broker_data":{


                "contract_size":

                contract_size,


                "tick_size":

                tick_size,


                "tick_value":

                tick_value,


                "volume_min":

                info.volume_min,


                "volume_max":

                info.volume_max,


                "volume_step":

                info.volume_step


            },



            "loss_per_lot":round(

                loss_per_lot,

                2

            ),



            "lot_size":lot_size



        }