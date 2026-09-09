import time
from datetime import datetime, timedelta

import MetaTrader5 as mt5

from app.execution.position_manager import PositionManager
from app.database.trade_history import TradeHistory



class TradeMonitor:


    def __init__(self):

        self.position_manager = PositionManager()

        self.trade_history = TradeHistory()

        self.running = False


        # AI trade memory

        self.trade_memory = {}





    def start(self):

        self.running = True


        print(
            "AI Trade Monitor Started"
        )



        while self.running:


            try:


                # Sync closed trades first

                self.sync_closed_trades()



                positions = self.position_manager.get_positions()



                if positions:


                    for position in positions:

                        self.manage_position(position)



                else:


                    print(
                        "No open positions"
                    )



                time.sleep(5)



            except Exception as e:


                print(
                    "Trade Monitor Error:",
                    str(e)
                )


                time.sleep(5)








    def stop(self):

        self.running = False


        print(
            "AI Trade Monitor Stopped"
        )








    def sync_closed_trades(self):


        open_trades = self.trade_history.get_open_trades()



        if not open_trades:

            return





        for trade in open_trades:



            # Support dictionary and tuple database formats

            if isinstance(trade, dict):

                ticket = trade["ticket"]


            else:

                ticket = trade[1]





            position = mt5.positions_get(
                ticket=ticket
            )



            # Still active

            if position:

                continue






            deals = mt5.history_deals_get(

                datetime.now() - timedelta(days=7),

                datetime.now()

            )



            if not deals:

                continue






            closing_deal = None




            for deal in deals:


                if (

                    deal.position_id == ticket

                    and deal.entry == 1

                ):


                    closing_deal = deal

                    break







            if closing_deal:



                exit_price = closing_deal.price

                profit = closing_deal.profit




                result = self.trade_history.close_trade(

                    ticket,

                    exit_price,

                    profit

                )



                print(

f"""
============================

TRADE CLOSED SYNC

Ticket:
{ticket}

Exit:
{exit_price}

Profit:
{profit}

Result:
{result["result"]}

============================

"""

                )









    def manage_position(self, position):


        ticket = position["ticket"]

        symbol = position["symbol"]

        entry = position["entry_price"]

        current = position["current_price"]

        stop_loss = position["stop_loss"]

        take_profit = position["take_profit"]

        trade_type = position["type"]

        profit = position["profit"]




        self.update_trade_memory(
            position
        )





        print(
f"""
----------------------------

Monitoring Trade

Ticket:
{ticket}

Symbol:
{symbol}

Type:
{trade_type}

Entry:
{entry}

Current:
{current}

Profit:
{profit}

SL:
{stop_loss}

TP:
{take_profit}

----------------------------
"""
        )





        self.check_break_even(
            position
        )



        self.check_trailing_stop(
            position
        )









    def update_trade_memory(self, position):


        ticket = position["ticket"]



        if ticket not in self.trade_memory:


            self.trade_memory[ticket] = {


                "highest_profit":
                    position["profit"],


                "lowest_profit":
                    position["profit"]

            }



        else:


            memory = self.trade_memory[ticket]



            if position["profit"] > memory["highest_profit"]:


                memory["highest_profit"] = position["profit"]




            if position["profit"] < memory["lowest_profit"]:


                memory["lowest_profit"] = position["profit"]












    def check_break_even(self, position):


        entry = position["entry_price"]

        current = position["current_price"]

        trade_type = position["type"]

        ticket = position["ticket"]



        activation_distance = 10





        if trade_type == "buy":



            if current >= entry + activation_distance:



                if position["stop_loss"] < entry:



                    print(
                        "BUY break-even activated"
                    )



                    self.move_stop_loss(

                        ticket,

                        entry

                    )







        elif trade_type == "sell":



            if current <= entry - activation_distance:



                if position["stop_loss"] > entry:



                    print(
                        "SELL break-even activated"
                    )



                    self.move_stop_loss(

                        ticket,

                        entry

                    )









    def check_trailing_stop(self, position):


        current = position["current_price"]

        entry = position["entry_price"]

        trade_type = position["type"]

        ticket = position["ticket"]



        trailing_distance = 5





        if trade_type == "buy":



            new_sl = current - trailing_distance




            if (

                current > entry

                and new_sl > position["stop_loss"]

            ):



                print(
                    "Updating BUY trailing stop"
                )



                self.move_stop_loss(

                    ticket,

                    new_sl

                )






        elif trade_type == "sell":



            new_sl = current + trailing_distance




            if (

                current < entry

                and new_sl < position["stop_loss"]

            ):



                print(
                    "Updating SELL trailing stop"
                )



                self.move_stop_loss(

                    ticket,

                    new_sl

                )









    def move_stop_loss(
        self,
        ticket,
        new_stop
    ):



        positions = mt5.positions_get(

            ticket=ticket

        )



        if not positions:


            return False





        position = positions[0]





        request = {


            "action":
                mt5.TRADE_ACTION_SLTP,


            "position":
                ticket,


            "symbol":
                position.symbol,


            "sl":
                round(
                    new_stop,
                    position.digits
                ),


            "tp":
                position.tp

        }






        result = mt5.order_send(
            request
        )





        if result is None:


            print(
                "SL update failed: No response"
            )


            return False






        if result.retcode != mt5.TRADE_RETCODE_DONE:



            print(

                "SL update failed:",

                result.comment

            )


            return False





        print(

            "Stop loss updated:",

            new_stop

        )



        return True