import sqlite3

from datetime import datetime

from pathlib import Path





DATABASE_PATH = Path("trade_history.db")







class TradeHistory:





    def __init__(self):


        self.create_tables()

        self.upgrade_database()







    # =====================================
    # DATABASE CONNECTION
    # =====================================


    def connect(self):


        connection = sqlite3.connect(
            DATABASE_PATH
        )


        connection.row_factory = sqlite3.Row


        return connection







    # =====================================
    # CREATE TABLES
    # =====================================


    def create_tables(self):


        connection = self.connect()

        cursor = connection.cursor()





        cursor.execute(
        """

        CREATE TABLE IF NOT EXISTS trades
        (

            id INTEGER PRIMARY KEY AUTOINCREMENT,


            ticket INTEGER UNIQUE,


            deal INTEGER,


            magic INTEGER,


            symbol TEXT,


            direction TEXT,


            volume REAL,


            entry_price REAL,


            exit_price REAL,


            stop_loss REAL,


            take_profit REAL,


            profit REAL DEFAULT 0,


            confidence INTEGER DEFAULT 0,


            setup_quality TEXT,


            strategy TEXT,


            ai_reason TEXT,


            risk_percent REAL,


            risk_reward REAL,


            status TEXT DEFAULT 'OPEN',


            result TEXT,


            opened_at TEXT,


            closed_at TEXT,


            updated_at TEXT


        )


        """
        )








        cursor.execute(
        """

        CREATE TABLE IF NOT EXISTS trade_events

        (

            id INTEGER PRIMARY KEY AUTOINCREMENT,


            ticket INTEGER,


            event TEXT,


            old_value TEXT,


            new_value TEXT,


            created_at TEXT


        )


        """
        )






        connection.commit()

        connection.close()







    # =====================================
    # SAFE MIGRATION
    # =====================================


    def upgrade_database(self):


        connection = self.connect()

        cursor = connection.cursor()



        cursor.execute(
            "PRAGMA table_info(trades)"
        )



        columns = [

            row["name"]

            for row in cursor.fetchall()

        ]





        required = {


            "deal":"INTEGER",


            "magic":"INTEGER",


            "setup_quality":"TEXT",


            "ai_reason":"TEXT",


            "risk_percent":"REAL",


            "risk_reward":"REAL"


        }





        for column, datatype in required.items():


            if column not in columns:


                cursor.execute(

                    f"""

                    ALTER TABLE trades

                    ADD COLUMN {column} {datatype}

                    """

                )






        connection.commit()

        connection.close()







    # =====================================
    # SAVE NEW TRADE
    # =====================================


    def save_trade(
        self,
        trade
    ):


        connection = self.connect()

        cursor = connection.cursor()



        now = datetime.utcnow().isoformat()



        cursor.execute(

        """

        INSERT OR REPLACE INTO trades


        (

            ticket,

            deal,

            magic,

            symbol,

            direction,

            volume,

            entry_price,

            stop_loss,

            take_profit,

            confidence,

            setup_quality,

            strategy,

            ai_reason,

            risk_percent,

            risk_reward,

            status,

            opened_at,

            updated_at


        )


        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)


        """,

        (



            trade.get("ticket"),


            trade.get("deal"),


            trade.get(
                "magic",
                202609
            ),


            trade["symbol"],


            trade["direction"],


            trade["volume"],


            trade["entry_price"],


            trade["stop_loss"],


            trade["take_profit"],


            trade.get(
                "confidence",
                0
            ),


            trade.get(
                "setup_quality",
                "unknown"
            ),


            trade.get(
                "strategy",
                "AI Strategy"
            ),


            trade.get(
                "ai_reason",
                ""
            ),


            trade.get(
                "risk_percent",
                1
            ),


            trade.get(
                "risk_reward",
                0
            ),


            "OPEN",


            now,


            now


        )

        )





        connection.commit()

        connection.close()





        return {


            "status":"saved",


            "ticket":trade["ticket"]

        }









    # =====================================
    # SAVE AI EVENT
    # =====================================


    def add_event(
        self,
        ticket,
        event,
        old_value=None,
        new_value=None
    ):


        connection = self.connect()

        cursor = connection.cursor()



        cursor.execute(

        """

        INSERT INTO trade_events

        (

            ticket,

            event,

            old_value,

            new_value,

            created_at

        )


        VALUES (?,?,?,?,?)


        """,

        (

            ticket,

            event,

            str(old_value),

            str(new_value),

            datetime.utcnow().isoformat()

        )

        )





        connection.commit()

        connection.close()







    # =====================================
    # CLOSE TRADE
    # =====================================


    def close_trade(
        self,
        ticket,
        exit_price,
        profit
    ):


        result = (

            "WIN"

            if profit > 0

            else

            "LOSS"

        )



        connection = self.connect()

        cursor = connection.cursor()



        now=datetime.utcnow().isoformat()



        cursor.execute(

        """

        UPDATE trades

        SET

        exit_price=?,


        profit=?,


        result=?,


        status=?,


        closed_at=?,


        updated_at=?


        WHERE ticket=?


        """,

        (

            exit_price,

            profit,

            result,

            "CLOSED",

            now,

            now,

            ticket

        )

        )





        connection.commit()

        connection.close()





        return {


            "status":"closed",


            "ticket":ticket,


            "result":result,


            "profit":profit

        }









    # =====================================
    # GET OPEN TRADES
    # =====================================


    def get_open_trades(self):


        return self.query(

            """

            SELECT *

            FROM trades

            WHERE status='OPEN'

            ORDER BY id DESC

            """

        )









    # =====================================
    # GET CLOSED TRADES
    # =====================================


    def get_closed_trades(self):


        return self.query(

            """

            SELECT *

            FROM trades

            WHERE status='CLOSED'

            ORDER BY id DESC

            """

        )









    # =====================================
    # GET ALL
    # =====================================


    def get_all_trades(self):


        return self.query(

            """

            SELECT *

            FROM trades

            ORDER BY id DESC

            """

        )









    def query(self, sql):


        connection=self.connect()

        cursor=connection.cursor()



        cursor.execute(sql)



        rows=cursor.fetchall()



        connection.close()



        return [

            dict(row)

            for row in rows

        ]








    # =====================================
    # FIND TRADE
    # =====================================


    def get_trade_by_ticket(
        self,
        ticket
    ):


        connection=self.connect()

        cursor=connection.cursor()



        cursor.execute(

        """

        SELECT *

        FROM trades

        WHERE ticket=?

        """,

        (ticket,)

        )



        row=cursor.fetchone()



        connection.close()



        return dict(row) if row else None







    # =====================================
    # DELETE
    # =====================================


    def delete_trade(
        self,
        ticket
    ):


        connection=self.connect()

        cursor=connection.cursor()



        cursor.execute(

        """

        DELETE FROM trades

        WHERE ticket=?

        """,

        (ticket,)

        )



        connection.commit()

        connection.close()



        return {


            "status":"deleted",

            "ticket":ticket

        }







    def get_history(self):

        return self.get_all_trades()