import sqlite3
from datetime import datetime
import pandas as pd
from typing import Literal


# local imports
from decorators import try_catch, error_handler
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
                File_Name           CHAR        NOT NULL,
                Format              CHAR        NOT NULL,
                Card_Number         CHAR        NOT NULL,
                Date                DATE        NOT NULL,
                New_Transactions    INT                 ,
                Transaction_count   INT         NOT NULL,
                Last_update         DATE        NOT NULL,
                PRIMARY KEY(File_Name, Format, Card_Number)
                );""") # Should also add card as primary key for 2 holders of the same format, trying to upload
                # a file for the same month for 2 different cards

            cls.__instance.cursor.execute("""
                CREATE TABLE IF NOT EXISTS TableMeta (
                ID                  INTEGER         PRIMARY KEY ,
                File_Name           CHAR            NOT NULL    ,
                Format              CHAR            NOT NULL    ,
                Card_Number         CHAR            NOT NULL    ,
                Initial_index       INT             NOT NULL    ,
                Initial_col         INT             NOT NULL    ,
                Row_count           INT             NOT NULL    ,
                Bad_rows            CHAR                        ,
                FOREIGN KEY(File_Name, Format, Card_Number)    REFERENCES File(File_Name, Format, Card_Number)
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
                Description         CHAR                    ,            
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
                Description         CHAR                    ,
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
                               file_name: str,
                               file_format: str,
                               card_number: str,
                               initial_index: str,
                               initial_col: int,
                               row_count: int,
                               bad_rows: str):
        """
        Insert meta data about a table.
        A table could be one or more transactions taken from the same file and
        it is defined by the index of its first row, source file name and number of transactions.
        Tables are created according to specific parameters in the code.
        """
        self.cursor.execute("""
            INSERT INTO TableMeta(File_Name, Format, Card_Number, Initial_index, Initial_col, Row_count, Bad_rows)
            VALUES(?, ?, ?, ?, ?, ?, ?)""", (file_name, file_format, card_number, initial_index, initial_col, row_count, bad_rows))

    def get_table_Meta(self, file_name: str, format_name: str, card_number: str ):
        """
        Return a list of table's meta data according to the given file name.
        """
        query = """ SELECT *
                    From TableMeta
                    WHERE File_name = ?
                    AND Format = ?
                    AND Card_number = ?
                """
        res = self.cursor.execute(query, (file_name, format_name, card_number, )).fetchall()
        res_dicts = []
        for item in res:
            res_dicts.append(dict(zip([d[0] for d in self.cursor.description], item)))
        return res_dicts

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
                    format_name: str,
                    card_number: str,
                    date: datetime,
                    new_trans_count: int,
                    trans_count: int):
        '''
        Insert a new file to local DB.
        @date: date stated in excel file.
        '''
        last_update = datetime.now().strftime("%d-%m-%Y")
        self.cursor.execute(f"""
            INSERT INTO File(File_Name, Format, Card_Number, Date, New_Transactions, Transaction_count, Last_update)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """, (name, format_name, card_number, date, new_trans_count, trans_count, last_update)
            )

    def set_new_trans_count(self, file_name: str, count: int) -> bool:
        self.cursor.execute("""UPDATE File
                               SET New_Transactions = :count
                               WHERE File_Name = :file_name""",
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

    def is_file_exists(self, file_name: str, file_format: str = None, card_number: str = '') -> bool:
        '''
        Returns True if a record with @file_name exists in the File table,
        False otherwise.

        In case file format is inserted, file existion will be checked according to both name and format.
        '''
        utils.log("warning.... card number is not being used..", 'warning')
        if file_format is None:
            ans = self.cursor.execute("""
                        SELECT 1
                        FROM File
                        WHERE File_Name = ?;
                    """, (file_name,)).fetchone()
            
        else:
            ans = self.cursor.execute("""
                        SELECT 1
                        FROM File
                        WHERE File_Name = ?
                        AND Format = ?;
                    """, (file_name, file_format,)).fetchone()

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
    def get_data_by_file_name(self, file_name: str, card_number: str):
        """
        return all transactions parsed from the file.
        """
        lst1 = self.cursor.execute("""
                                    SELECT ID,
                                        'BankTransactions' AS TableName,
                                        Name,
                                        Date, Value_Date,
                                        Ref, Out, Income, Balance,
                                        Category
                                    FROM BankTransactions
                                    WHERE source_file = ?"""
                                   , (file_name,)).fetchall()
        lst2 = self.cursor.execute("""
                                    SELECT ID,
                                        'CardTransactions' AS TableName,
                                        Name,
                                        CardID,
                                        Executed_Date, Charge_Date,
                                        Charge_Value, Charge_Currency,
                                        Transaction_Value, Value_Currency, Extra_info,
                                        Category
                                    FROM CardTransactions
                                    WHERE source_file = ?
                                    AND CardID = ?""", (file_name, card_number, )).fetchall()
        return lst1 + lst2
    
    @error_handler(default_return=-99999)
    def get_latest_Balance(self) -> int:
        """

        """
        return self.cursor.execute("""SELECT Balance FROM BankTransactions
                                      ORDER BY Date
                                      DESC LIMIT 1
                                   """).fetchone()[0]

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
                                        Description AS 'Description/Charge_Currency',
                                        Reserved AS 'Reserved/Value_Currency',
                                        Date AS 'Date/Executed_Date',
                                        Value_Date AS 'Value_Date/Charge_Date',
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
                                        Charge_Currency,
                                        Value_Currency,
                                        Executed_Date,
                                        Charge_Date,
                                        Extra_info
                                   FROM CardTransactions
                                   WHERE Category = ?
                                   """,
                                   (cat_name, cat_name)).fetchall(), \
            [d[0] for d in self.cursor.description]

    def get_monthly_earnings(self, year: int, month: int, category=None) -> pd.DataFrame:
        """
        The function receives a year, a month and a category name
        and returns all the Spending transactions associated with the given categories in the given date
        in the same month only. 
        If category is None, transaction will not be filtered by category.
        """
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        day1 = datetime(year, month, 1).strftime('%Y-%m-%d %H:%M:%S')
        day2 = datetime(year, month, last_day).strftime('%Y-%m-%d %H:%M:%S')

        # (Transaction_Value*Charge_Value < 0 
        # AND Charge_Date >= ? AND Charge_Date <= ?)
        # This section is ment for retriving refund issued to the credit card.
        data = self.cursor.execute("""
                                    SELECT
                                        ID,
                                        'BankTransactions' AS TableName,
                                        Ref AS 'Ref/CardID',
                                        Name,
                                        Date AS 'Date/Executed_Date',
                                        Value_Date AS 'Value_Date/Charge_Date',
                                        Out AS 'Out/Transaction_value',
                                        Income AS 'Income/Charge_Value',
                                        Description AS 'Description/Charge_Currency',
                                        Reserved AS 'Reserved/Value_Currency',
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
                                        Charge_Currency,
                                        Value_Currency,
                                        Category,
                                        Extra_Info,
                                        Source_file
                                    FROM CardTransactions
                                    WHERE (Executed_Date >= ?
                                    AND Executed_Date <= ?
                                    AND Transaction_Value < 0)
                                    OR (Transaction_Value*Charge_Value < 0 
                                    AND Charge_Date >= ? AND Charge_Date <= ?)
                                    """, (day1, day2, "אשראי", day1, day2, day1, day2)).fetchall()
        
        df = pd.DataFrame(data, columns=[d[0] for d in self.cursor.description])
        if category is not None:
            df = df[df['Category'] == category]
        return df

    def get_monthly_spendings(self, year: int, month: int, category=None) -> pd.DataFrame:
        """
        The function receives a year, a month and a category name
        and returns all the Earnings transactions associated with the given categories in the given date
        in the same month only. 
        If category is None, transaction will not be filtered by category.
        """
        import calendar
        
        # When looking for spendings. transaction will be queried by the date they will be 
        # effective in the bank account and not by the date they were exectued.
        # That is why, when given month x, we will search for transactions in month x + 1


        last_day = calendar.monthrange(year, month)[1]
        b_init = datetime(year, month, 1).strftime('%Y-%m-%d %H:%M:%S')
        b_end = datetime(year, month, last_day).strftime('%Y-%m-%d %H:%M:%S')
        next_month =  utils.next_month(datetime(year, month, 1)).month
        next_month = '0' + str(next_month) if len(str(next_month)) == 1 else str(next_month)
        
        # last_day = calendar.monthrange(fit_year, fit_month)[1]
        # bt_init = datetime(fit_year, fit_month, 1).strftime('%Y-%m-%d %H:%M:%S')
        # bt_end = datetime(fit_year, fit_month, last_day).strftime('%Y-%m-%d %H:%M:%S')
        # Notes about the sql command:
        # in the cardtransaction table:
        #   1. The following condition might not be relevant: (Executed_Date >= ? AND Executed_Date <= ?)
        #   2. Card transaction which represent spendings will always be positive.
        data = self.cursor.execute("""
                                    SELECT
                                        'BankTransactions' AS TableName,
                                        Ref AS 'Ref/CardID',
                                        Name,
                                        Date AS 'Date/Executed_Date',
                                        Value_Date AS 'Value_Date/Charge_Date',
                                        Out AS 'Out/Transaction_value',
                                        Income AS 'Income/Charge_Value',
                                        Description AS 'Description/Charge_Currency',
                                        Reserved AS 'Reserved/Value_Currency',
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
                                        Charge_Currency,
                                        Value_Currency,
                                        Category,
                                        Extra_Info,
                                        Source_file
                                    FROM CardTransactions
                                    WHERE Transaction_Value > 0 AND (
                                        (Executed_Date >= ? AND Executed_Date <= ?)
                                        OR 
                                        (strftime('%m', Charge_Date) = ?)
                                    )
                                    """, (b_init, b_end, "אשראי", b_init, b_end, next_month, )).fetchall()
        df = pd.DataFrame(data, columns=[d[0] for d in self.cursor.description])
        if category is not None:
            df = df[df['Category'] == category]
        return df

    def get_spendings(self, category=None) -> pd.DataFrame:
        """
        The function receives a category and returns all spending transactions that are associated with this category.
        If category argument is None - all spending trasnactions will be returned.
        the dataframed format fits the process_prices function.
        """
        if not (isinstance(category, str) or category is None):
            utils.log("Argument input error in 'get_spendings'", "error")

        data = self.cursor.execute("""
                                    SELECT
                                        'BankTransactions' AS TableName,
                                        Ref AS 'Ref/CardID',
                                        Name,
                                        Date AS 'Date/Executed_Date',
                                        Value_Date AS 'Value_Date/Charge_Date',
                                        Out AS 'Out/Transaction_value',
                                        Income AS 'Income/Charge_Value',
                                        Description AS 'Description/Charge_Currency',
                                        Reserved AS 'Reserved/Value_Currency',
                                        Category,
                                        Extra_Info,
                                        Source_file
                                    FROM BankTransactions
                                    WHERE 
                                        Out != 0
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
                                        Charge_Currency,
                                        Value_Currency,
                                        Category,
                                        Extra_Info,
                                        Source_file
                                    FROM CardTransactions
                                    WHERE 
                                        Transaction_Value > 0 
                                        """, ("אשראי", )).fetchall()      
        df = pd.DataFrame(data, columns=[d[0] for d in self.cursor.description])
        if category is not None:
            df = df[df['Category'] == category]
        return df  

    # Query NOTE: Executed_Date > 0 (In the CardTransaction table) represents only Negative transaction since Negative transactions
    # appears with a positive value in the Card table.

    def get_transactions(self, category=None, business=None):
        """
        TODO
        """
        if not (isinstance(category, str) or category is None):
            utils.log("Argument input 'category' error in 'get_transactions'", "error")
        
        if not (isinstance(business, str) or business is None):
            utils.log("Argument input 'business' error in 'get_transactions'", "error")

        data = self.cursor.execute("""
                                    SELECT
                                        'BankTransactions' AS TableName,
                                        Ref AS 'Ref/CardID',
                                        Name,
                                        Date AS 'Date/Executed_Date',
                                        Value_Date AS 'Value_Date/Charge_Date',
                                        Out AS 'Out/Transaction_value',
                                        Income AS 'Income/Charge_Value',
                                        Description AS 'Description/Charge_Currency',
                                        Reserved AS 'Reserved/Value_Currency',
                                        Category,
                                        Extra_Info,
                                        Source_file
                                    FROM BankTransactions
                                    WHERE Category != ?
                                    UNION ALL
                                    SELECT
                                        'CardTransactions' AS TableName,
                                        CardID,
                                        Name,
                                        Executed_Date,
                                        Charge_Date,
                                        Transaction_Value,
                                        Charge_Value,
                                        Charge_Currency,
                                        Value_Currency,
                                        Category,
                                        Extra_Info,
                                        Source_file
                                    FROM CardTransactions
                                    WHERE 
                                        Transaction_Value > 0 
                                        """, ("אשראי", )).fetchall()  
        df = pd.DataFrame(data, columns=[d[0] for d in self.cursor.description])
        
        if category is not None:
            df = df[df['Category'] == category]
        
        if business is not None:
            df = df[df['Name'] == business]

        return df

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
                                    SELECT File_Name, Format, Card_Number, Last_update
                                    From File
                                    """).fetchall()
        return [tup[0:4] for tup in res] # to get result as list

    def get_file_names_by(self, format_name: str, card_number: str):
        """
        get file names by format name and card,
        can return more than one file.
        """
        res = self.cursor.execute("""
                                    SELECT File_Name
                                    FROM File
                                    WHERE Format = ?
                                    AND Card_Number = ?
                                    """, (format_name, card_number,)).fetchall()
        
        return [tup[0] for tup in res] # to get result as list

    def drop_file(self, file_name: str, format_name: str, card_number: str):
        """
        Remove the enteries associated with the file name from the db.
        """
        self.cursor.execute("""
                            DELETE
                            From File
                            WHERE File_Name = ?
                            AND Format = ?
                            AND Card_Number = ?
                            """, (file_name, format_name, card_number,))
        self.cursor.execute("""
                            DELETE
                            From BankTransactions
                            WHERE source_file = ?
                            """, (file_name,))
        self.cursor.execute("""
                            DELETE
                            From CardTransactions
                            WHERE source_file = ?
                            AND CardID = ?
                            """, (file_name, card_number,))
        self.cursor.execute("""
                            DELETE
                            From TableMeta
                            WHERE File_Name = ?
                            AND Format = ?
                            AND Card_Number = ?                            
                            """, (file_name, format_name, card_number, ))

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
                utils.log(f"Bad input {table} in 'set_category' in DataBase class", "error")

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

    def set_transaction_description(self, desc: str, TableName: str, id: int) -> None:
        """
        The function sets the description field of the trasaction Given its id and table.
        """
        query = """
                    UPDATE {}
                    SET Description = ?
                    WHERE ID = ?
                """.format(TableName)
        self.cursor.execute(query, (desc, id))

    def card_sum(self, date: datetime):
        """
        TODO... what does this fucntion do?
        """
        m_2 = '0' + str(date.month) if len(str(date.month)) == 1 else str(date.month)
        
        m_1, y_1 = utils.subtract_month(date.month, date.year)
        m_0, y_0 = utils.subtract_month(int(m_1), int(y_1))
        nxt_month, rlvnt_year = utils.next_month(date).month, utils.next_month(date).year
        nxt_month = '0' + str(nxt_month) if len(str(nxt_month)) == 1 else str(nxt_month)
        rlvnt_year = str(rlvnt_year)
        # Executed_Date AS 'Date/Executed_Date',
        # Charge_Date AS 'Value_Date/Charge_Date'
        # AS key word is added in order to match the 'process_prices' function
        data = self.cursor.execute("""
                            SELECT 'CardTransactions' AS TableName,
                                   CardID,
                                   Executed_Date AS 'Date/Executed_Date',
                                   Charge_Date AS 'Value_Date/Charge_Date',
                                   Charge_Value AS 'Income/Charge_Value',
                                   Charge_Currency AS 'Description/Charge_Currency',
                                   Value_Currency AS 'Reserved/Value_Currency',
                                   Transaction_Value AS 'Out/Transaction_value'
                            FROM CardTransactions
                            WHERE (strftime('%m', Charge_Date) = ? AND strftime('%Y', Charge_Date) = ?)
                            """, (nxt_month, rlvnt_year, )).fetchall() # TODO can this be simplified for just the transactions at the set charge date?
        return data, [d[0] for d in self.cursor.description]

    def get_Bank_Transactions(self, day: int, month: int, year: int):
        """
        Get all bank transactions of month @month and year @year,
        day is not relevant.
        """
        str_month = str(month)
        if len(str_month) == 1:
            str_month = '0' + str_month
        str_day = str(day)
        if len(str_day) == 1:
            str_day = '0' + str_day
        data = self.cursor.execute("""
                            SELECT ID, Name, Date, Ref, Out, Category FROM BankTransactions
                            WHERE strftime('%m', Date) = ?
                            AND strftime('%Y', Date) = ?
                            """, (str_month, str(year), )).fetchall()
                            # AND strftime('%d', Date) = ?
        return pd.DataFrame(data=data, columns=[d[0] for d in self.cursor.description])

    def get_card_ids(self) -> list:
        """
        Returns all card id's in the data base in a list format.
        """
        data = self.cursor.execute(""" SELECT CardID FROM Card""").fetchall()
        return [x[0] for x in data]

    def execute_query(self, query: str) -> bool:
        try:
            self.cursor.execute(query)
            return True
        except Exception as e:
            return False
        
    def get_all_business_names(self) -> list:
        """
        Returns all business names in the data base in a list format.
        """
        card_business = self.cursor.execute("""
                                   SELECT DISTINCT Name
                                   FROM CardTransactions 
                                   """).fetchall()
        
        bank_business = self.cursor.execute("""
                                   SELECT DISTINCT Name
                                   FROM BankTransactions 
                                   """).fetchall()
        card_business_list = [x[0] for x in card_business]
        bank_business_list = [y[0] for y in bank_business]
        all_businesses = card_business_list + bank_business_list
        return all_businesses
         
    def get_all_category_names(self) -> list:
        """
        Returns all categories names in the data base in a list format.
        """
        combined_categories_query = """
                                    SELECT DISTINCT Category
                                    FROM (
                                        SELECT Category FROM CardTransactions
                                        UNION
                                        SELECT Category FROM BankTransactions
                                    ) AS CombinedCategories
                                    """
        self.cursor.execute(combined_categories_query)
        unique_categories = self.cursor.fetchall()
        #card_categories = self.cursor.execute("""
             #                       SELECT DISTINCT Category
            #                        FROM CardTransactions
             #                       """).fetchall()
        
        #bank_categories = self.cursor.execute("""
         #                           SELECT DISTINCT Category
          #                          FROM BankTransactions
           #                         """).fetchall()
        #card_categories_list = [x[0] for x in card_categories]
        #bank_categories_list = [y[0] for y in bank_categories]
        #all_categories =  list(set(card_categories_list + bank_categories_list))
        unique_categories_list = [x[0] for x in unique_categories]
        return unique_categories_list
        
  
    def months_total_calculator(self) -> int:
        """
        Returns the amount of months when transacations had taken
        """
        return int(self.cursor.execute("""
                            SELECT
                            ROUND((julianday(MAX(Charge_Date)) - julianday(MIN(Charge_Date))) / 30, 0)  + 1
                            FROM CardTransactions 
                            """).fetchone()[0])
    
    def total_spendings(self, name_for_analysis: str, case: Literal[0, 1]) -> float:
        """
        Returns the total amount of spendings from both card and bank data tables.
        The value is returned as a positive value.
        """
        if case not in [0, 1]:
            utils.log("Bad Argument in function 'total_spendings', case should be 0 or 1", 'error')

        condition = "Name" if case else "Category"

        query = f"""
            SELECT SUM(sum_i)
            FROM (
                SELECT Out AS sum_i
                FROM BankTransactions
                WHERE {condition} = ?
            UNION ALL
                SELECT Transaction_Value AS sum_i
                FROM CardTransactions
                WHERE {condition} = ? AND Transaction_Value > 0
                ) AS merged_table 
                """
        return self.cursor.execute(query, (name_for_analysis, name_for_analysis,)).fetchone()[0]
    

    def total_income(self, name_for_analysis: str, case: Literal[0, 1]) -> float:
        """
        Returns the total sum of all spendings of a chosen category \ business transactions
        case 0: Category
        case 1: Business
        """
        if case not in [0, 1]:
            utils.log("Bad Argument in function 'total_spendings', case should be 0 or 1", 'error')

        condition = "Name" if case else "Category"

        query = f"""
                SELECT SUM(sum_i)
                FROM (
                    SELECT Income AS sum_i
                    FROM BankTransactions
                    WHERE {condition} = ?
                UNION ALL
                    SELECT Transaction_Value AS sum_i
                    FROM CardTransactions
                    WHERE {condition} = ? AND Transaction_Value < 0
                    ) AS merged_table 
                    """
        return self.cursor.execute(query, (name_for_analysis, name_for_analysis,)).fetchone()[0]
    

    def total_sum_transactions(self, name_for_analysis: str, case: Literal[0, 1]) -> float:
        """
        The function calculate the total sum of transactions taken from both card and bank tables.
        All transactions taken from the card data base are calculated as negative variables.
        @name_for_analysis will query only transactions with the given category set.
        @case - 0 is for querying the category column, 1 is for querying the name column.
        """
        if case not in [0, 1]:
            utils.log("Bad Argument in function 'total_sum_transactions', case should be 0 or 1", 'error')

        condition = "Name" if case else "Category"

        query = f"""
            SELECT SUM(sum_i)
            FROM (
                SELECT Income - Out AS sum_i
                FROM BankTransactions
                WHERE {condition} = ?
            UNION ALL
                SELECT -Transaction_Value AS sum_i
                FROM CardTransactions
                WHERE {condition} = ?
                ) AS merged_table
            """
        return self.cursor.execute(query, (name_for_analysis, name_for_analysis,)).fetchone()[0]


    def bank_transactions_sum_list(self, name_for_analysis: str, case: Literal[0, 1]) -> pd.DataFrame:
        """
        The function receives category/business name
        and returns a list of sums
        where sum_i is the sum of all the transactions in year_i, month_i for the given category/business name
        """
        if case not in [0, 1]:
            utils.log("Bad Argument in function 'total_sum_transactions', case should be 0 or 1", 'error')

        condition = "Name" if case else "Category"

        query = f"""
            SELECT SUM(sum_i), year, month
            FROM (
                SELECT Income + Out AS sum_i, strftime('%Y', Date) AS year, strftime('%m', Date) AS month
                FROM BankTransactions
                WHERE {condition} = ?
            UNION ALL
                SELECT Transaction_Value AS sum_i, strftime('%Y', Executed_Date) AS year, strftime('%m', Executed_Date) AS month
                FROM CardTransactions
                WHERE {condition} = ?
                ) AS merged_table
            GROUP BY year, month
            ORDER BY year, month
            """
        data = self.cursor.execute(query, (name_for_analysis, name_for_analysis,)).fetchall()
        print(data)
        return pd.DataFrame(data=data, columns=[d[0] for d in self.cursor.description])
        
# ----------------------------------------------------------------------
#                            User SQL commands
# ----------------------------------------------------------------------
    def change_category_by_id(self) -> None:
        param1 = utils.template_menu(['Bank', 'Card'], msg='Choose the relevant table:')
        param2 = input('Insert transaction ID:')
        param3, _ = utils.handle_categories()
        if param1 == 0:
            query = """SELECT * FROM BankTransactions WHERE id = ?"""
            prev = self.cursor.execute(query, (param2,)).fetchall()
            
            query = """UPDATE BankTransactions SET category = ? WHERE id = ?"""            
            self.cursor.execute(query, (param3, param2,)).fetchall()
            
            query = """SELECT * FROM BankTransactions WHERE id = ?"""
            after = self.cursor.execute(query, (param2,)).fetchall()
        else:   # 1
            query = """SELECT * FROM CardTransactions WHERE id = ?"""
            prev = self.cursor.execute(query, (param2,)).fetchall()
            
            query = """UPDATE CardTransactions SET category = ? WHERE id = ?"""            
            self.cursor.execute(query, (param3, param2,)).fetchall()
            
            query = """SELECT * FROM CardTransactions WHERE id = ?"""
            after = self.cursor.execute(query, (param2,)).fetchall()

        utils.log(f"Before: {prev}")
        utils.log(f"After: {after}")        


# ----------------------------------------------------------------------
# ----------------------------------------------------------------------

    def commit_changes(self) -> None:
        self.connection.commit()
