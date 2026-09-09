import MetaTrader5 as mt5


class TPSLOptimizer:


    MIN_RR = 2

    MIN_STOP_DISTANCE = 5





    def optimize(self, trade):


        symbol = trade["symbol"]


        direction = str(
            trade["direction"]
        ).lower()





        # =====================================
        # SYMBOL VALIDATION
        # =====================================


        info = mt5.symbol_info(symbol)



        if info is None:


            return {


                "status":"error",


                "message":
                f"Symbol {symbol} unavailable"

            }






        if not info.visible:


            if not mt5.symbol_select(
                symbol,
                True
            ):


                return {


                    "status":"error",


                    "message":
                    f"Unable to activate {symbol}"

                }








        # =====================================
        # LIVE MARKET PRICE
        # =====================================


        tick = mt5.symbol_info_tick(
            symbol
        )



        if tick is None:


            return {


                "status":"error",


                "message":
                "Unable to get live market price"

            }







        if direction in [

            "buy",

            "long"

        ]:


            entry = tick.ask




        elif direction in [

            "sell",

            "short"

        ]:


            entry = tick.bid





        else:


            return {


                "status":"error",


                "message":
                "Invalid direction"

            }









        # =====================================
        # AI LEVELS
        # =====================================


        old_entry = trade.get(
            "entry_price",
            entry
        )


        old_sl = trade.get(
            "stop_loss"
        )


        old_tp = trade.get(
            "take_profit"
        )







        if old_sl is None:


            return {


                "status":"error",


                "message":
                "Stop loss missing"

            }







        # =====================================
        # RISK DISTANCE
        # =====================================


        risk_distance = abs(

            old_entry -

            old_sl

        )





        if risk_distance <= 0:


            return {


                "status":"error",


                "message":
                "Invalid risk distance"

            }







        # =====================================
        # CREATE NEW SL FROM LIVE PRICE
        # =====================================


        if direction in [

            "buy",

            "long"

        ]:


            stop_loss = entry - risk_distance



        else:


            stop_loss = entry + risk_distance








        # =====================================
        # CHECK EXISTING AI TP
        # =====================================


        keep_existing_tp = False



        if old_tp is not None:


            reward = abs(

                old_tp -

                old_entry

            )


            rr = reward / risk_distance



            if rr >= self.MIN_RR:


                keep_existing_tp = True







        if keep_existing_tp:


            take_profit = old_tp



            risk_reward = round(

                rr,

                2

            )



        else:


            if direction in [

                "buy",

                "long"

            ]:


                take_profit = (

                    entry +

                    (

                        risk_distance *

                        self.MIN_RR

                    )

                )


            else:


                take_profit = (

                    entry -

                    (

                        risk_distance *

                        self.MIN_RR

                    )

                )



            risk_reward = self.MIN_RR







        # =====================================
        # MINIMUM STOP CHECK
        # =====================================


        if risk_distance < self.MIN_STOP_DISTANCE:


            return {


                "status":"error",


                "message":
                f"Stop distance too small ({risk_distance})"

            }







        # =====================================
        # PRICE NORMALIZATION
        # =====================================


        digits = info.digits



        entry = round(

            entry,

            digits

        )


        stop_loss = round(

            stop_loss,

            digits

        )


        take_profit = round(

            take_profit,

            digits

        )







        # =====================================
        # FINAL OUTPUT
        # =====================================


        return {


            "status":

            "optimized",



            "symbol":

            symbol,



            "direction":

            direction,



            "entry_price":

            entry,



            "original_entry":

            old_entry,



            "original_stop_loss":

            old_sl,



            "original_take_profit":

            old_tp,



            "stop_loss":

            stop_loss,



            "take_profit":

            take_profit,



            "risk":

            round(

                risk_distance,

                3

            ),



            "risk_reward":

            risk_reward,



            "message":

            "TP/SL optimized using live MT5 execution price"

        }