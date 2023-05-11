import sqlite3
from datetime import datetime

# local imports
from decorators import try_catch
from src_utils.utils import utils
from Constants import Local
from typing import Tuple


class DataBase:

    __instance = None
    connection: sqlite3.Connection
    cursor: sqlite3.Cursor

    def __new__(cls):
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)
            cls.__instance.connection = sqlite3.connect('databse.db')
            cls.__instance.cursor = cls.__instance.connection.cursor()
            cls.__instance.cursor.execute("""
                CREATE TABLE IF NOT EXISTS Card (
                cardID          CHAR(4)     PRIMARY KEY,
                description     TEXT
                );""")
            cls.__instance.cursor.execute("""
                CREATE TABLE IF NOT EXISTS File (
                Name                CHAR        NOT NULL PRIMARY KEY,
                Date                DATE        NOT NULL,
                Description         CHAR                ,
                New_Transactions    INT                 ,
                Transaction_count   INT         NOT NULL,
                Last_update         DATE        NOT NULL
                );""")

            cls.__instance.cursor.execute("""
                CREATE TABLE IF NOT EXISTS TableMeta (
                ID                  INTEGER         PRIMARY KEY ,
                source_file         CHAR            NOT NULL    ,
                Initial_index       INT             NOT NULL    ,
                Row_count           INT             NOT NULL    ,
                FOREIGN KEY(source_file)    REFERENCES File(Name)
                );""")

            cls.__instance.cursor.execute("""
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
                Ex_description      CHAR        NOT NULL    ,
                Category            CHAR                    ,
                FOREIGN KEY(source_file)    REFERENCES File(Name)
                );""")

            cls.__instance.cursor.execute("""
                CREATE TABLE IF NOT EXISTS Transactions (
                ID                  INTEGER     PRIMARY KEY ,
                cardID              CHAR(4)                 ,
                transaction_date    DATE        NOT NULL    ,
                business_name       CHAR                    ,
                amount              INT         NOT NULL    ,
                transaction_type    CHAR                    ,
                charge_date         DATE        NOT NULL    ,
                charge_amount       INT         NOT NULL    ,
                source_file         CHAR        NOT NULL    ,
                description         TEXT                    ,
                Category            CHAR                    ,
                FOREIGN KEY(cardID)         REFERENCES Card(cardID),
                FOREIGN KEY(source_file)    REFERENCES File(Name)
                );""")

        return cls.__instance

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
        Insert a new Bank transaction to local DB.
        BankTransactions are transaction taken from the BankTransaction File.
        '''
        self.cursor.execute(f"""
            INSERT INTO BankTransactions
            (Ref, Date, Date_value, Source_Dest, Amount, Balance, Description, source_file, Ex_description, Category)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (ref, date, date_value, source_dest, amount, balance, desc, source_file, '', 'Uncategorized')
            )

    def insert_table_meta_data(self,
                               source_file_name: str,
                               initial_index: int,
                               row_count: int):
        """
        Insert meta data about a table.
        A table could be one or more transactions taken from the same file and
        it is defined by the index of its first row, source file name and number of transactions.
        Tables are created accoreding to specific parameters in the code.
        """
        self.cursor.execute("""
            INSERT INTO TableMeta(source_file, Initial_index, Row_count)
            VALUES(?, ?, ?)""", (source_file_name, initial_index, row_count))

    def get_table_Meta(self, file_name: str):
        """
        Return a list of table's meta data according to the given file name.
        """
        query = """ SELECT *
                    From TableMeta
                    WHERE source_file = ?
                """
        return self.cursor.execute(query, (file_name,)).fetchall()

    def insert_transaction(self,
                           cardID: str,
                           transaction_date: datetime,
                           business_name: str,
                           amount: int,
                           transaction_type: str,
                           charge_date: datetime,
                           charge_amount: int,
                           source_file: str):
        '''
        Insert a new transaction to the data base.
        Currently, the transactions are inserted from the Files associated with credit files,
        into the Transactions data base.
        The function also checks it the associated credit card is present in the db.
        '''
        if not self.is_card_exists(cardID):
            utils.log(f'New card found: ->{cardID}<-', 'db')
            if not self.insert_card(cardID, "Auto Insertion"):
                return False
            utils.log(f'Card ID {cardID} has been added!', 'db')

        query = """ INSERT INTO Transactions
                    (cardID, transaction_date, business_name, amount, transaction_type, charge_date, charge_amount,
                        source_file, description, Category)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
        self.cursor.execute(query,
                            (cardID, transaction_date, business_name, amount, transaction_type, charge_date,
                                charge_amount, source_file, '', 'Uncategorized'))

    def insert_file(self,
                    name: str,
                    date: datetime,
                    description: str,
                    new_trans_count: int,
                    trans_count: int):
        '''
        Insert a new file to local DB.
        '''
        last_update = datetime.now()
        self.cursor.execute(f"""
            INSERT INTO File(Name, Date, Description, New_Transactions, Transaction_count, Last_update)
            VALUES(?, ?, ?, ?, ?, ?)
            """, (name, date, description, new_trans_count, trans_count, last_update)
            )

    def set_new_trans_count(self, file_name: str, count: int) -> bool:
        self.cursor.execute("""UPDATE File
                               SET New_Transactions = :count
                               WHERE Name = :file_name""",
                            {'count': count,
                             'file_name': file_name})
        return True

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

    def is_file_exists(self, file_name: str) -> bool:
        '''
        Returns True if a record with @file_name exists in the File table,
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
        query = """ SELECT Transaction_count
                    FROM File
                    WHERE Name = ?;
                """
        return self.cursor.execute(query, (file_name,)).fetchone()[0]

    @try_catch
    def close(self):
        '''
        Close The connection to the database.
        '''
        self.connection.close()

    # TODO: this function is currently not being used anywhere.
    def get_data_by_file_name(self, file_name: str):
        """
        return all transactions parsed from the file.
        """
        lst1 = self.cursor.execute("SELECT * FROM BankTransactions WHERE source_file = ?", (file_name,)).fetchall()
        lst2 = self.cursor.execute("SELECT * FROM Transactions WHERE source_file = ?", (file_name,)).fetchall()
        return lst1 + lst2

    def get_table_stats(self, file_name: str):
        """
        Return a list of the table stats of the @file_name
        """
        return self.cursor.execute("""
                                    SELECT header_idx, idx_2, idx_3, idx_4
                                    From File
                                    WHERE Name = ?
                                    """, (file_name,)).fetchall()[0]

    def get_latest_bank_transaction(self):
        """

        """
        return self.cursor.execute("""SELECT * FROM BankTransactions
                                      ORDER BY Date
                                      DESC LIMIT 1
                                   """).fetchall()[0]

    def get_gas_related(self, keys: list, year: str = "", month: str = ""):
        rows = []
        for k in keys:
            rows += self.cursor.execute("""
                                        SELECT transaction_date,business_name,amount FROM Transactions
                                        WHERE business_name = ?
                                        """, (k,)).fetchall()
        return rows

    def get_by_category(self, cat_name: str) -> list[Tuple[str, str, int, str, str, str]]:
        """
        Get all transactions by category name.
        Transactions format is: (source_table, Source_Dest, Amount, Category, Date, Description)
        """
        return self.cursor.execute("""
                                   SELECT 'BankTransactions' as source_table, Source_Dest, Amount, Category, Date, Description
                                   FROM BankTransactions WHERE Category = ?
                                   UNION ALL
                                   SELECT 'Transactions' as source_table, business_name, amount, Category, transaction_date, Description
                                   FROM Transactions WHERE Category = ? """,
                                   (cat_name, cat_name)).fetchall()

    # def get_transactions(self, table: str, year: int, month: int):
    #     """
    #     The function will query all the records from the given month from the given
    #     table @table. Table = "BankTransactions" for the BankTransaction table and any
    #     other string for the Transaction table.

    #     @param year - the year in format 20XX
    #     @param month - the month in format XX
    #     @param table - the table to query.
    #     """
    #     import calendar
    #     last_day = calendar.monthrange(year, month)[1]
    #     day1 = datetime(year, month, 1).strftime('%Y-%m-%d %H:%M:%S')
    #     day2 = datetime(year, month, last_day).strftime('%Y-%m-%d %H:%M:%S')
    #     if table == "BankTransactions":
    #         return self.cursor.execute("select * from BankTransactions where date >= ? and date <= ?", (day1, day2)).fetchall()
    #     else:
    #         return self.cursor.execute("select * from Transactions where charge_date >= ? and charge_date <= ?", (day1, day2)).fetchall()

    def get_monthly_earnings(self, year: int, month: int) -> list[Tuple[str, int, str, str]]:
        """
        Input:
        An year and a month.
        returns all Income transaactions in the same month.
        Output:
        a list with tuples containing: (Name, Amount, Category, Date)
        """
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        day1 = datetime(year, month, 1).strftime('%Y-%m-%d %H:%M:%S')
        day2 = datetime(year, month, last_day).strftime('%Y-%m-%d %H:%M:%S')
        return self.cursor.execute("""
                                    SELECT Source_Dest, Amount, Category, Date
                                    FROM BankTransactions
                                    WHERE date >= ?
                                    AND date <= ?
                                    AND Amount > 0""", (day1, day2)).fetchall()
    
    def get_monthly_spendings(self, year: int, month: int) -> list[Tuple[str, int, str, str]]:
        """
        The function will return a list containing all spendings made in the current month given.
        Spendings can be given from both BankTranssactions table of Transactions table.
        Template is: (Table name, Name, Card, Amount, Category, Date)

        For transaction Taken from the BankTransactions; card will appear as 'Bank'
        """
        import calendar
        
        # When looking for spendings. transaction will be queried by the date they will be 
        # effective in the bank account and not by the date they were exectued.
        # That is why, when given month x, we will search for transactions in month x + 1
        fit_month = month % 12 + 1
        if fit_month == 1:
            fit_year = year + 1
        else:
            fit_year = year

        last_day = calendar.monthrange(year, month)[1]
        b_init = datetime(year, month, 1).strftime('%Y-%m-%d %H:%M:%S')
        b_end = datetime(year, month, last_day).strftime('%Y-%m-%d %H:%M:%S')
        
        last_day = calendar.monthrange(fit_year, fit_month)[1]
        bt_init = datetime(fit_year, fit_month, 1).strftime('%Y-%m-%d %H:%M:%S')
        bt_end = datetime(fit_year, fit_month, last_day).strftime('%Y-%m-%d %H:%M:%S')
        return self.cursor.execute("""
                                    SELECT 'BankTransactions' AS source_table, Source_Dest,
                                    'Bank' AS Card, amount, Category, Date
                                    FROM BankTransactions
                                    WHERE date >= ?
                                    AND date <= ?
                                    AND amount < 0
                                    AND (Category != ? OR Category IS NULL)
                                    UNION ALL
                                    SELECT 'Transactions' AS source_table, business_name, cardID,
                                    Amount, Category, transaction_date
                                    FROM Transactions
                                    WHERE transaction_date >= ?
                                    AND transaction_date <= ?
                                    """, (b_init, b_end, "אשראי", b_init, b_end,)).fetchall()

    def get_all_transactions(self, shift: int = 5, income: bool = True):
        """

        """
        import calendar
        from dateutil.relativedelta import relativedelta

        today = datetime.now()
        day1 = (today - relativedelta(months=shift)).replace(day=1).strftime('%Y-%m-%d %H:%M:%S')

        last_day = calendar.monthrange(today.year, today.month)[1]
        day2 = datetime(today.year, today.month, last_day).strftime('%Y-%m-%d %H:%M:%S')
        if income:
            return self.cursor.execute("SELECT Amount, Date from BankTransactions where Amount > 0 AND date >= ? and date <= ?", (day1, day2)).fetchall()
        else:
            trans = self.cursor.execute("SELECT Amount, transaction_date from Transactions where transaction_date >= ? and transaction_date <= ?", (day1, day2)).fetchall()
            bank_trans = self.cursor.execute("""SELECT Amount, Date
                                                FROM BankTransactions
                                                WHERE Amount < 0
                                                AND date >= ?
                                                AND date <= ?
                                                AND Category != ?""", (day1, day2, "אשראי")).fetchall()
            return trans + bank_trans

    def get_visa_transactions(self):
        """
        """
        items = []
        for word in Local.VISA_KEY_WORDS:
            items += self.cursor.execute("""
                                        SELECT Date,Source_Dest,Amount,Balance FROM BankTransactions
                                        WHERE Source_Dest = ?
                                        """, (word,)).fetchall()
        return items

    def get_file_names(self):
        """
        """
        res = self.cursor.execute("""
                                    SELECT Name
                                    From File
                                    """).fetchall()
        return [tup[0] for tup in res]

    def drop_file(self, file_name: str):
        """
        """
        self.cursor.execute("""
                            DELETE
                            From File
                            WHERE Name = ?
                            """, (file_name,))
        self.cursor.execute("""
                            DELETE
                            From BankTransactions
                            WHERE source_file = ?
                            """, (file_name,))
        self.cursor.execute("""
                            DELETE
                            From Transactions
                            WHERE source_file = ?
                            """, (file_name,))
        self.cursor.execute("""
                            DELETE
                            From TableMeta
                            WHERE source_file = ?
                            """, (file_name,))
        self.connection.commit()

    def get_untagged(self) -> list:
        """
        Get all untagged items in database.
        An untagged item is a transaction with no category
        """
        res1 = self.cursor.execute("""
                                    SELECT 'BankTransactions' as TableName,
                                    ID, Date, Source_Dest, Amount, Description
                                    FROM BankTransactions
                                    WHERE (Category IS NULL OR Category IS Uncategorized)
                                    ORDER BY ID DESC
                                    """).fetchall()
        res2 = self.cursor.execute("""
                                    SELECT 'Transactions' as TableName,
                                    ID, transaction_date, business_name, amount, transaction_type
                                    FROM Transactions
                                    WHERE (Category IS NULL OR Category IS Uncategorized)
                                    ORDER BY ID DESC
                                    """).fetchall()
        
        # Sortion order is made for better handling of tagging
        # x[2] is the location of the Date
        sorted_list = sorted(res1 + res2, key=lambda x: x[2], reverse=True)
        return sorted_list

    def set_category(self, table: str, id: int, category: str):
        """
        Set a tag for a transaction with a given id.
        """
        match table:
            case "Transactions":
                self.cursor.execute("""
                                    UPDATE Transactions
                                    SET Category = ?
                                    WHERE ID = ?
                                    """, (category, id,))
            case "BankTransactions":
                self.cursor.execute("""
                                    UPDATE BankTransactions
                                    SET Category = ?
                                    WHERE ID = ?
                                    """, (category, id,))
            case _:
                utils.log("Bad input in 'set_category' in DataBase class", "error")

    def commit_changes(self) -> None:
        self.connection.commit()


