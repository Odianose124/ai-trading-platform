import MetaTrader5 as mt5





class MarketPriceService:





    MAX_SPREAD_POINTS = 500





    def get_price(self, symbol, direction):


        """
        Get live MT5 execution price


        BUY  -> Ask price

        SELL -> Bid price


        Used before TP/SL calculation
        """






        # =====================================
        # CHECK MT5 CONNECTION
        # =====================================


        terminal = mt5.terminal_info()



        if terminal is None:


            return {


                "status":"error",


                "message":

                "MT5 terminal unavailable"


            }







        # =====================================
        # CHECK SYMBOL
        # =====================================


        info = mt5.symbol_info(symbol)



        if info is None:


            return {


                "status":"error",


                "message":

                f"Symbol {symbol} unavailable"


            }







        # =====================================
        # ACTIVATE SYMBOL
        # =====================================


        if not info.visible:


            selected = mt5.symbol_select(

                symbol,

                True

            )



            if not selected:


                return {


                    "status":"error",


                    "message":

                    f"Unable to activate {symbol}"


                }







        # =====================================
        # GET LIVE MARKET DATA
        # =====================================


        tick = mt5.symbol_info_tick(symbol)





        if tick is None:


            return {


                "status":"error",


                "message":

                "Unable to get live market tick"


            }







        # =====================================
        # CHECK MARKET PRICE
        # =====================================


        if tick.ask <= 0 or tick.bid <= 0:


            return {


                "status":"error",


                "message":

                "Invalid market price"


            }








        direction = str(direction).lower()







        # =====================================
        # SELECT EXECUTION PRICE
        # =====================================


        if direction in [


            "buy",

            "long"


        ]:


            execution_price = tick.ask





        elif direction in [


            "sell",

            "short"


        ]:


            execution_price = tick.bid





        else:


            return {


                "status":"error",


                "message":

                "Invalid trade direction"


            }








        # =====================================
        # SPREAD CHECK
        # =====================================


        spread = tick.ask - tick.bid



        spread_points = spread / info.point






        if spread_points > self.MAX_SPREAD_POINTS:


            return {


                "status":"blocked",


                "message":

                f"Spread too high ({spread_points:.0f} points)",


                "spread":

                spread_points


            }







        # =====================================
        # NORMALIZE PRICE
        # =====================================


        execution_price = round(

            execution_price,

            info.digits

        )




        bid = round(

            tick.bid,

            info.digits

        )



        ask = round(

            tick.ask,

            info.digits

        )







        return {


            "status":"success",



            "symbol":

            symbol,



            "direction":

            direction,



            "price":

            execution_price,



            "bid":

            bid,



            "ask":

            ask,



            "digits":

            info.digits,



            "spread":

            round(

                spread,

                info.digits

            ),



            "spread_points":

            round(

                spread_points,

                2

            )



        }