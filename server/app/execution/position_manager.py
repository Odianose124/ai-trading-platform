import MetaTrader5 as mt5





class PositionManager:



    def __init__(self):

        self.magic_number = 202609







    # =====================================
    # MT5 CONNECTION
    # =====================================


    def ensure_connection(self):


        terminal = mt5.terminal_info()



        if terminal is None:


            return mt5.initialize()



        return True







    # =====================================
    # GET AI POSITIONS
    # =====================================


    def get_positions(
        self,
        symbol=None
    ):


        if not self.ensure_connection():


            return []




        positions = mt5.positions_get()



        if positions is None:


            return []





        result = []




        for position in positions:



            if position.magic != self.magic_number:


                continue





            if symbol and position.symbol != symbol:


                continue





            position_type = (

                "buy"

                if position.type == mt5.POSITION_TYPE_BUY

                else

                "sell"

            )





            result.append({



                "ticket":

                position.ticket,



                "symbol":

                position.symbol,



                "type":

                position_type,



                "volume":

                position.volume,



                "entry_price":

                position.price_open,



                "current_price":

                position.price_current,



                "stop_loss":

                position.sl,



                "take_profit":

                position.tp,



                "profit":

                position.profit,



                "swap":

                position.swap,



                "magic":

                position.magic



            })





        return result







    # =====================================
    # MODIFY POSITION SL / TP
    # =====================================


    def modify_position(
        self,
        ticket,
        stop_loss,
        take_profit=None
    ):


        positions = mt5.positions_get(
            ticket=ticket
        )



        if not positions:


            return {


                "status":"error",


                "message":"Position not found"


            }




        position = positions[0]




        if take_profit is None:


            take_profit = position.tp





        request = {



            "action":

            mt5.TRADE_ACTION_SLTP,



            "position":

            ticket,



            "symbol":

            position.symbol,



            "sl":

            stop_loss,



            "tp":

            take_profit


        }





        result = mt5.order_send(request)




        if result is None:


            return {


                "status":"failed",


                "message":"Modification failed"


            }





        if result.retcode != mt5.TRADE_RETCODE_DONE:


            return {


                "status":"failed",


                "retcode":result.retcode,


                "message":result.comment


            }







        return {


            "status":"success",


            "ticket":ticket,


            "new_stop_loss":stop_loss,


            "take_profit":take_profit


        }









    # =====================================
    # MOVE STOP LOSS TO BREAK EVEN
    # =====================================


    def move_to_break_even(
        self,
        ticket
    ):



        positions = mt5.positions_get(
            ticket=ticket
        )



        if not positions:


            return {


                "status":"error",


                "message":"Position not found"


            }





        position = positions[0]





        return self.modify_position(

            ticket,

            position.price_open,

            position.tp

        )









    # =====================================
    # AUTO BREAK EVEN CHECK
    # =====================================


    def check_break_even(
        self,
        profit_distance=5
    ):


        positions = self.get_positions()



        actions = []





        for position in positions:



            entry = position["entry_price"]


            current = position["current_price"]





            if position["type"] == "buy":


                movement = current - entry



            else:


                movement = entry - current





            if movement >= profit_distance:



                result = self.move_to_break_even(

                    position["ticket"]

                )


                actions.append(result)







        return actions







    # =====================================
    # TRAILING STOP
    # =====================================


    def trailing_stop(
        self,
        trail_distance=3
    ):



        positions = self.get_positions()



        actions = []





        for position in positions:



            current = position["current_price"]



            old_sl = position["stop_loss"]



            ticket = position["ticket"]





            if position["type"] == "buy":



                new_sl = current - trail_distance





                if old_sl == 0 or new_sl > old_sl:



                    result = self.modify_position(

                        ticket,

                        new_sl,

                        position["take_profit"]

                    )


                    actions.append(result)







            else:



                new_sl = current + trail_distance





                if old_sl == 0 or new_sl < old_sl:



                    result = self.modify_position(

                        ticket,

                        new_sl,

                        position["take_profit"]

                    )


                    actions.append(result)








        return actions







    # =====================================
    # POSITION SUMMARY
    # =====================================


    def summary(self):


        positions = self.get_positions()



        total_profit = sum(

            p["profit"]

            for p in positions

        )



        total_volume = sum(

            p["volume"]

            for p in positions

        )





        return {



            "open_trades":

            len(positions),



            "total_volume":

            total_volume,



            "floating_profit":

            round(

                total_profit,

                2

            )

        }