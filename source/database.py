import sqlite3
from datetime import datetime
import pandas as pd

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
            cls.__instance.connection = sqlite3.connect(f'{Local.DB_NAME}.db')
            cls.__instance.cursor = cls.__instance.connection.cursor()
            cls.__instance.cursor.execute("""
                CREATE TABLE IF NOT EXISTS Card (
                CardID          CHAR(4)     PRIMARY KEY,
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
                Initial_col         INT             NOT NULL    ,
                Row_count           INT             NOT NULL    ,
                FOREIGN KEY(source_file)    REFERENCES File(Name)
                );""")

            cls.__instance.cursor.execute("""
                CREATE TABLE IF NOT EXISTS BankTransactions (
                ID                  INTEGER     PRIMARY KEY ,
                Date                DATE        NOT NULL    ,
                Value_Date          DATE                    ,
                Name                CHAR        NOT NULL    ,
                Ref                 CHAR                    ,
                Out                 INT         NOT NULL    ,
                Income              INT         NOT NULL    ,
                Balance             INT                     ,
                Extra_Info          CHAR                    ,
                Source_file         CHAR        NOT NULL    ,
                Category            CHAR                    ,
                Reserved            INT                     ,
                FOREIGN KEY(source_file)    REFERENCES File(Name)
                );""")

            cls.__instance.cursor.execute("""
                CREATE TABLE IF NOT EXISTS CardTransactions (
                ID                  INTEGER     PRIMARY KEY ,
                CardID              CHAR        NOT NULL    ,
                Name                CHAR        NOT NULL    ,
                Executed_Date       DATE        NOT NULL    ,
                Charge_Date         DATE                    ,
                Charge_Value        INT                     ,
                Charge_Currency     CHAR                    ,
                Transaction_Value   INT                     ,
                Value_Currency      CHAR                    ,
                Extra_Info          CHAR                    ,
                Source_file         CHAR        NOT NULL    ,
                Category            CHAR                    ,
                Reserved            INT                     ,
                FOREIGN KEY(CardID)         REFERENCES Card(CardID),
                FOREIGN KEY(source_file)    REFERENCES File(Name)
                );""")
            # Charge value - The initial value/ The total sum of payments of the transaction.
            # Transaction value - The actual amount credited for

        return cls.__instance

    def insert_bank_transaction(self,
                                Date: datetime,
                                Value_Date: datetime,
                                Name: str,
                                Ref: str,
                                Out: float,
                                Income: float,
                                Balance: float,
                                Source_file: str,
                                Extra_Info: str = "None",
                                Category: str = "NotCategorized"):
        '''
        Insert a new Bank transaction to local DB.
        BankTransactions are transaction taken from the BankTransaction File.
        '''

        query = """ INSERT INTO BankTransactions(
                Date,
                Value_Date,
                Name,
                Ref,
                Out,
                Income,
                Balance,
                Extra_Info,
                Source_file,
                Category)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        self.cursor.execute(query, (
                                Date,
                                Value_Date,
                                Name,
                                Ref,
                                Out,
                                Income,
                                Balance,
                                Extra_Info,
                                Source_file,
                                Category)
                            )

    def insert_table_meta_data(self,
                               source_file_name: str,
                               initial_index: int,
                               initial_col: int,
                               row_count: int):
        """
        Insert meta data about a table.
        A table could be one or more transactions taken from the same file and
        it is defined by the index of its first row, source file name and number of transactions.
        Tables are created according to specific parameters in the code.
        """
        self.cursor.execute("""
            INSERT INTO TableMeta(source_file, Initial_index, Initial_col, Row_count)
            VALUES(?, ?, ?, ?)""", (source_file_name, initial_index, initial_col, row_count))

    def get_table_Meta(self, file_name: str):
        """
        Return a list of table's meta data according to the given file name.
        """
        query = """ SELECT *
                    From TableMeta
                    WHERE source_file = ?
                """
        return self.cursor.execute(query, (file_name,)).fetchall()
    
    def insert_card_transaction(self,
                                CardID: str,
                                Name: str,
                                Executed_Date: datetime,
                                Charge_Date: datetime,
                                Charge_Value: float,
                                Source_file: str,
                                Charge_Currency: str = "NotSpecified",
                                Transaction_Value: float = 0.00,
                                Value_Currency: str = "NotSpecified",
                                Extra_Info: str = "None",
                                Category: str = "NotCategorized"
                                ):
        '''
        Insert a new transaction to the data base.
        Currently, the transactions are inserted from the Files associated with credit files,
        into the Transactions data base.
        The function also checks it the associated credit card is present in the db.
        '''
        if not self.is_card_exists(CardID):
            utils.log(f'New card found: ->{CardID}<-', 'db')
            if not self.insert_card(CardID, "Auto Insertion"):
                return False
            utils.log(f'Card ID {CardID} has been added!', 'db')

        query = """ INSERT INTO CardTransactions(
                        CardID,
                        Name,
                        Executed_Date,
                        Charge_Date,
                        Charge_Value,
                        Charge_Currency,
                        Transaction_Value,
                        Value_Currency,
                        Extra_Info,
                        Source_file,
                        Category)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
        self.cursor.execute(query, (
                                CardID,
                                Name,
                                Executed_Date,
                                Charge_Date,
                                Charge_Value,
                                Charge_Currency,
                                Transaction_Value,
                                Value_Currency,
                                Extra_Info,
                                Source_file,
                                Category)
                            )

    def insert_file(self,
                    name: str,
                    date: datetime,
                    description: str,
                    new_trans_count: int,
                    trans_count: int):
        '''
        Insert a new file to local DB.
        @date: date stated in excel file.
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

    def get_by_category(self, cat_name: str) -> Tuple[list, list]:
        """
        Get all transactions by category name.
        Transactions format is: (source_table, Source_Dest, Amount, Category, Date, Description)
        """
        return self.cursor.execute("""
                                   SELECT
                                        'BankTransactions' AS TableName,
                                        Name,
                                        Out AS 'Out/Transaction_value',
                                        Income AS 'Income/Charge_Value',
                                        Category,
                                        Date,
                                        Extra_Info
                                   FROM BankTransactions
                                   WHERE Category = ?
                                   UNION ALL
                                   SELECT
                                        'CardTransactions' AS TableName,
                                        Name,
                                        Transaction_value,
                                        Charge_Value,
                                        Category,
                                        Executed_Date,
                                        Extra_info
                                   FROM CardTransactions
                                   WHERE Category = ?
                                   """,
                                   (cat_name, cat_name)).fetchall(), \
            [d[0] for d in self.cursor.description]

    def get_monthly_earnings(self, year: int, month: int) -> Tuple[list, list]:
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
                                    SELECT
                                        ID,
                                        'BankTransactions' AS TableName,
                                        Ref AS 'Ref/CardID',
                                        Name,
                                        Date,
                                        Value_Date AS 'Value_Date/Charge_Date',
                                        Out AS 'Out/Transaction_value',
                                        Income AS 'Income/Charge_Value',
                                        Category,
                                        Extra_Info,
                                        Source_file
                                    FROM BankTransactions
                                    WHERE Date >= ?
                                    AND Date <= ?
                                    AND Income != 0
                                    AND (Category != ? OR Category IS NULL)
                                    UNION ALL
                                    SELECT
                                        ID,
                                        'CardTransactions' AS TableName,
                                        CardID,
                                        Name,
                                        Executed_Date,
                                        Charge_Date,
                                        Transaction_Value,
                                        Charge_Value,
                                        Category,
                                        Extra_Info,
                                        Source_file
                                    FROM CardTransactions
                                    WHERE Executed_Date >= ?
                                    AND Executed_Date <= ?
                                    AND Transaction_Value < 0
                                    """, (day1, day2, "אשראי", day1, day2)).fetchall(), \
            [d[0] for d in self.cursor.description]

    def get_monthly_earnings_sum(self, year: int, month: int) -> int:
        """
        Input:
        An year and a month.

        Returns the total earning sums of the month.
        """
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        day1 = datetime(year, month, 1).strftime('%Y-%m-%d %H:%M:%S')
        day2 = datetime(year, month, last_day).strftime('%Y-%m-%d %H:%M:%S')

        return self.cursor.execute("""
                                     SELECT ROUND(COALESCE(subquery1.x, 0) + COALESCE(subquery2.y, 0), 2) AS 'total_sum'
                                        FROM
                                            (SELECT SUM(Income) AS 'x'
                                             FROM BankTransactions
                                             WHERE Date >= ?
                                             AND Date <= ?
                                             AND Category != ?) AS subquery1
                                        JOIN
                                            (SELECT SUM(Transaction_Value) AS 'y'
                                             FROM CardTransactions
                                             WHERE Executed_Date >= ?
                                             AND Executed_Date <= ?
                                             AND Transaction_Value < 0) AS subquery2;
                                    """, (day1, day2, "אשראי", day1, day2)).fetchone()[0]

    def get_monthly_spendings(self, year: int, month: int) -> Tuple[list, list]:
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
        
        # last_day = calendar.monthrange(fit_year, fit_month)[1]
        # bt_init = datetime(fit_year, fit_month, 1).strftime('%Y-%m-%d %H:%M:%S')
        # bt_end = datetime(fit_year, fit_month, last_day).strftime('%Y-%m-%d %H:%M:%S')
        return self.cursor.execute("""
                                    SELECT
                                        'BankTransactions' AS TableName,
                                        Ref AS 'Ref/CardID',
                                        Name,
                                        Date,
                                        Value_Date AS 'Value_Date/Charge_Date',
                                        Out AS 'Out/Transaction_value',
                                        Income AS 'Income/Charge_Value',
                                        Category,
                                        Extra_Info,
                                        Source_file
                                    FROM BankTransactions
                                    WHERE Date >= ?
                                    AND Date <= ?
                                    AND Out != 0
                                    AND (Category != ? OR Category IS NULL)
                                    UNION ALL
                                    SELECT
                                        'CardTransactions' AS TableName,
                                        CardID,
                                        Name,
                                        Executed_Date,
                                        Charge_Date,
                                        Transaction_Value,
                                        Charge_Value,
                                        Category,
                                        Extra_Info,
                                        Source_file
                                    FROM CardTransactions
                                    WHERE Executed_Date >= ?
                                    AND Executed_Date <= ?
                                    AND Transaction_Value > 0
                                    """, (b_init, b_end, "אשראי", b_init, b_end,)).fetchall(), \
            [d[0] for d in self.cursor.description]

    # Query NOTE: Executed_Date > 0 (In the CardTransaction table) represents only Negative transaction since Negative transactions
    # appears with a positive value in the Card table.

    def get_monthly_spendings_sum(self, year: int, month: int) -> int:
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

        return self.cursor.execute("""
                                     SELECT ROUND(COALESCE(subquery1.x, 0) + COALESCE(subquery2.y, 0)) AS 'total_sum'
                                        FROM
                                            (SELECT SUM(Out) AS 'x'
                                             FROM BankTransactions
                                             WHERE Date >= ?
                                             AND Date <= ?
                                             AND Category != ?) AS subquery1
                                        JOIN
                                            (SELECT SUM(Transaction_Value) AS 'y'
                                             FROM CardTransactions
                                             WHERE Executed_Date >= ?
                                             AND Executed_Date <= ?
                                             AND Transaction_Value > 0) AS subquery2;
                                    """, (b_init, b_end, "אשראי", b_init, b_end)).fetchone()[0]

    # Query NOTE: Executed_Date > 0 (In the CardTransaction table) represents only Negative transaction since Negative transactions
    # appears with a positive value in the Card table.

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
                            From CardTransactions
                            WHERE source_file = ?
                            """, (file_name,))
        self.cursor.execute("""
                            DELETE
                            From TableMeta
                            WHERE source_file = ?
                            """, (file_name,))

    def get_untagged(self) -> Tuple[list, list]:
        """
        Get all untagged items in database.
        An untagged item is a transaction with no category
        """
        res1 = self.cursor.execute("""
                                    SELECT
                                        'BankTransactions' as TableName,
                                        ID,
                                        Date,
                                        Name,
                                        Ref,
                                        Out,
                                        Income,
                                        Extra_Info,
                                        Source_file
                                    FROM BankTransactions
                                    WHERE Category IS 'NotCategorized'
                                    ORDER BY ID DESC
                                    """).fetchall()
        res2 = self.cursor.execute("""
                                    SELECT
                                        'CardTransactions' AS TableName,
                                        ID,
                                        Executed_Date,
                                        Name,
                                        CardID AS 'CardID/Ref',
                                        Charge_Value AS 'Charge_Value/Out',
                                        Transaction_Value AS 'Transaction_Value/Income' ,
                                        Extra_Info,
                                        Source_file
                                    FROM CardTransactions
                                    WHERE Category IS 'NotCategorized'
                                    ORDER BY ID DESC
                                    """).fetchall()
        
        # Sortion order is made for better handling of tagging
        # x[2] is the location of the Date
        sorted_list = sorted(res1 + res2, key=lambda x: x[2], reverse=True)
        return sorted_list, [d[0] for d in self.cursor.description]

    def set_category(self, table: str, id: int, category: str):
        """
        Set a tag for a transaction with a given id.
        """
        match table:
            case "CardTransactions":
                self.cursor.execute("""
                                    UPDATE CardTransactions
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

    def get_by_name(self, TableName: str, name: str):
        """
        WARNING - The function only returns transactions with no category.
        Get All transactions from the given table that has the same exact name.
        """
        query = """
                    SELECT *
                    FROM {}
                    WHERE Name = ?
                    AND Category IS 'NotCategorized'
                    """.format(TableName)
        return self.cursor.execute(query, (name,)).fetchall(), \
            [d[0] for d in self.cursor.description]

    def get_file_table(self) -> pd.DataFrame:

        data = self.cursor.execute("""
                                    SELECT *
                                    FROM File
                                    """).fetchall()
        return pd.DataFrame(data=data, columns=[d[0] for d in self.cursor.description])

    def get_file_format(self, name: str) -> str:
        return self.cursor.execute("""
                                   SELECT Description
                                   FROM file
                                   WHERE Name = ?
                                   """, (name,)).fetchone()[0]

    def commit_changes(self) -> None:
        self.connection.commit()


