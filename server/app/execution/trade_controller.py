import MetaTrader5 as mt5


from app.execution.mt5_executor import MT5Executor
from app.execution.position_manager import PositionManager

from app.database.trade_history import TradeHistory

from app.services.risk_gate import RiskGate
from app.services.lot_calculator import LotCalculator
from app.services.tp_sl_optimizer import TPSLOptimizer
from app.services.market_price_service import MarketPriceService







class TradeController:



    def __init__(self):


        self.executor = MT5Executor()

        self.position_manager = PositionManager()

        self.history = TradeHistory()

        self.risk_gate = RiskGate()

        self.lot_calculator = LotCalculator()

        self.tp_sl_optimizer = TPSLOptimizer()

        self.market_price_service = MarketPriceService()







    # =====================================
    # EXECUTE ENTRY POINT
    # =====================================


    def execute(self, trade):

        return self.execute_signal(trade)








    # =====================================
    # GET ACCOUNT BALANCE
    # =====================================


    def get_account_balance(self):


        account = mt5.account_info()


        if account is None:

            return None


        return account.balance











    # =====================================
    # COMPLETE AI TRADING PIPELINE
    # =====================================


    def execute_signal(self, signal):


        try:



            """
            AI Signal

                ↓

            Live Market Price

                ↓

            TP/SL Optimizer

                ↓

            Risk Gate

                ↓

            Balance Check

                ↓

            Lot Calculator

                ↓

            MT5 Execution

                ↓

            Result

            """





            # Keep AI signal untouched

            trade_signal = signal.copy()





            # =====================================
            # 1. GET LIVE MARKET PRICE
            # =====================================


            market = self.market_price_service.get_price(

                trade_signal["symbol"],

                trade_signal["direction"]

            )




            if market.get("status") != "success":


                return {

                    "status":"failed",

                    "stage":"market_price",

                    "message":market

                }






            # Save AI entry for analysis

            trade_signal["ai_entry_price"] = trade_signal.get(

                "entry_price"

            )



            # Replace with real MT5 price

            trade_signal["entry_price"] = market["price"]








            # =====================================
            # 2. TP / SL OPTIMIZATION
            # =====================================


            optimized = self.tp_sl_optimizer.optimize(

                trade_signal

            )





            if optimized.get("status") != "optimized":


                return {


                    "status":"blocked",

                    "stage":"tp_sl_optimizer",

                    "message":optimized

                }







            trade_signal["stop_loss"] = optimized["stop_loss"]


            trade_signal["take_profit"] = optimized["take_profit"]










            # =====================================
            # 3. RISK GATE
            # =====================================


            risk_result = self.risk_gate.evaluate(

                trade_signal

            )





            if not risk_result.get("approved"):



                reasons = risk_result.get(

                    "reasons",

                    []

                )



                return {


                    "status":"blocked",


                    "stage":"risk_gate",


                    "message":(

                        risk_result.get("reason")

                        or

                        (
                            reasons[0]

                            if reasons

                            else

                            "Risk rejected trade"

                        )

                    ),


                    "risk_result":risk_result,


                    "trade":trade_signal

                }









            # =====================================
            # 4. ACCOUNT BALANCE
            # =====================================


            balance = self.get_account_balance()





            if balance is None:



                return {


                    "status":"failed",


                    "stage":"account",


                    "message":

                    "Unable to get MT5 balance"

                }









            # =====================================
            # 5. LOT CALCULATION
            # =====================================


            lot_result = self.lot_calculator.calculate(



                balance=balance,


                risk_percent=trade_signal.get(

                    "risk_percent",

                    1

                ),



                entry_price=trade_signal["entry_price"],



                stop_loss=trade_signal["stop_loss"],



                symbol=trade_signal["symbol"]


            )








            if lot_result.get("status") != "calculated":



                return {


                    "status":"blocked",


                    "stage":"lot_calculator",


                    "message":lot_result

                }








            volume = lot_result["lot_size"]










            # =====================================
            # 6. EXECUTE MT5 ORDER
            # =====================================


            execution = self.executor.execute_trade(



                symbol=trade_signal["symbol"],



                direction=trade_signal["direction"],



                volume=volume,



                stop_loss=trade_signal["stop_loss"],



                take_profit=trade_signal["take_profit"]


            )







            if execution.get("status") != "executed":



                return {


                    "status":"failed",


                    "stage":"mt5_execution",


                    "message":execution

                }









            # =====================================
            # FINAL RESPONSE
            # =====================================


            return {


                "status":"success",



                "message":

                "AI trade executed successfully",




                "ai_signal":{


                    "entry_price":

                    trade_signal.get(

                        "ai_entry_price"

                    ),


                    "confidence":

                    trade_signal.get(

                        "confidence",

                        0

                    ),


                    "strategy":

                    trade_signal.get(

                        "strategy",

                        "AI Strategy"

                    )

                },




                "market_price":market,




                "account_balance":

                balance,




                "risk_percent":

                trade_signal.get(

                    "risk_percent",

                    1

                ),




                "tp_sl_optimizer":

                optimized,




                "risk_result":

                risk_result,




                "lot_calculation":

                lot_result,




                "execution":

                execution



            }







        except Exception as e:



            return {


                "status":"error",


                "stage":"trade_controller",


                "message":str(e)

            }









    # =====================================
    # ACTIVE POSITIONS
    # =====================================


    def get_active_positions(self):


        return self.position_manager.get_positions()