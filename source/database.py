import sqlite3
from datetime import datetime

# local imports
from decorators import try_catch
from Constants import log


class DataBase:

    def __init__(self):

        self.connection = sqlite3.connect('databse.db')
        self.cursor = self.connection.cursor()

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS Card (
            cardID          CHAR(4)     PRIMARY KEY,
            description     TEXT
            );""")

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS File (
            Name                CHAR        NOT NULL PRIMARY KEY,
            Date                DATE        NOT NULL,
            Description         CHAR                ,
            New_Transactions    INT                 ,
            Transaction_count   INT         NOT NULL,
            Header_idx          INT         NOT NULL,
            Last_update         DATE        NOT NULL
            );""")

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS BankTransactions (
            ID                  INTEGER        PRIMARY KEY ,
            Ref                 CHAR        NOT NULL    ,
            Date                DATE        NOT NULL    ,
            Date_value          DATE        NOT NULL    ,
            Source_Dest         CHAR        NOL NULL    ,
            Amount              INT         NOT NULL    ,
            Balance             INT         NOT NULL    ,
            Description         DATE                    ,
            source_file         CHAR        NOT NULL    ,
            Ex_description      CHAR        NOT NULL,
            FOREIGN KEY(source_file)    REFERENCES File(Name)
            );""")

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS Transactions (
            ID                  INTEGER     PRIMARY KEY ,
            cardID              CHAR(4)                 ,
            transaction_date    DATE        NOT NULL    ,
            business_name       CHAR                    ,
            amount              INT         NOT NULL    ,
            transaction_type    CHAR                    ,
            charge_date         DATE        NOT NULL    ,
            source_file         CHAR        NOT NULL    ,
            description         TEXT                    ,
            FOREIGN KEY(cardID)         REFERENCES Card(cardID),
            FOREIGN KEY(source_file)    REFERENCES File(Name)
            );""")

    def insert_bank_transaction(self,
                                ref: str,
                                date: datetime,
                                date_value: str,
                                source_dest: str,
                                amount: int,
                                balance: str,
                                desc: str,
                                source_file: str):
        '''
        Insert a new transaction to local DB.
        '''
        self.cursor.execute(f"""
            INSERT INTO BankTransactions(Ref, Date, Date_value, Source_Dest, Amount,
                Balance, Description, source_file, Ex_description)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (ref, date, date_value, source_dest, amount, balance,
                  desc, source_file, '')
            )
        self.connection.commit()

    def insert_transaction(self,
                           cardID: str,
                           transaction_date: datetime,
                           business_name: str,
                           amount: int,
                           transaction_type: str,
                           charge_date: datetime,
                           source_file: str):
        '''
        Insert a new transaction to local DB.
        '''
        if not self.is_card_exists(cardID):
            log(f'New card found: ->{cardID}<-', 'db')
            if not self.insert_card(cardID, "Auto Insertion"):
                return False
            log(f'Card ID {cardID} has been added!', 'db')

        self.cursor.execute(f"""
            INSERT INTO Transactions(cardID, transaction_date, business_name,
                amount, transaction_type, charge_date, source_file, description)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """, (cardID, transaction_date, business_name, amount,
                  transaction_type, charge_date, source_file, '')
            )
        self.connection.commit()

    def insert_file(self,
                    name: str,
                    date: datetime,
                    description: str,
                    new_trans_count: int,
                    trans_count: int,
                    header_idx: int):
        '''
        Insert a new file to local DB.
        '''
        last_update = datetime.now()
        self.cursor.execute(f"""
            INSERT INTO File(Name, Date, Description, New_Transactions, Transaction_count, Header_idx, Last_update)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """, (name, date, description, new_trans_count, trans_count, header_idx, last_update)
            )
        self.connection.commit()

    @try_catch
    def is_card_exists(self, cardID: str) -> bool:
        ans = self.cursor.execute("""
                    SELECT 1
                    FROM Card
                    WHERE cardID = ?;
                """, (cardID,)).fetchone()
        return False if ans is None else True

    @try_catch
    def insert_card(self,
                    id: str,
                    description: str):
        '''
        Insert a new card to local DB.
        '''
        self.cursor.execute(f"""
            INSERT INTO Card VALUES(?, ?)
            """, (id, description))
        self.connection.commit()

    def is_file_exists(self, file_name: str) -> bool:
        '''
        Returns True if a file with the given name exists.
        False otherwise.
        '''
        ans = self.cursor.execute("""
                    SELECT 1
                    FROM File
                    WHERE Name = ?;
                """, (file_name,)).fetchone()
        return False if ans is None else True

    @try_catch
    def total_transactions(self, file_name):
        '''
        Returns True if a file with the given date exists.
        False otherwise.
        '''
        return self.cursor.execute("""
                    SELECT Transaction_count
                    FROM File
                    WHERE Name = ?;
                """, (file_name,)).fetchone()[0]

    @try_catch
    def get_header_idx(self, file_name):
        '''
        Returns the header_idx value of @file_name,
        The header_idx represent the index of the header row.
        '''
        return self.cursor.execute("""
                    SELECT Header_idx
                    FROM File
                    WHERE Name = ?;
                """, (file_name,)).fetchone()[0]

    @try_catch
    def close(self):
        '''
        Close The connection to the database.
        '''
        self.connection.close()

# ----------------- Extracting Data from Db --------------------

    def get_transactions(self, table: str, year: int, month: int):
        """

        """
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        day1 = datetime(year, month, 1).strftime('%Y-%m-%d %H:%M:%S')
        day2 = datetime(year, month, last_day).strftime('%Y-%m-%d %H:%M:%S')
        if table == "BankTransactions":
            return self.cursor.execute("select * from BankTransactions where date >= ? and date <= ?", (day1, day2)).fetchall()
        else:
            return self.cursor.execute("select * from Transactions where transaction_date >= ? and transaction_date <= ?", (day1, day2)).fetchall()
