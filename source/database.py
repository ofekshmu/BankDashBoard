import sqlite3
import threading
from datetime import datetime
import pandas as pd
from typing import Literal, Optional
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import DictCursor

load_dotenv()


# local imports
from decorators import try_catch, error_handler
from src_utils.utils import utils
from Constants import Local, Paths
from typing import Tuple


# PostgreSQL connection
def get_db_connection():
    """Get PostgreSQL connection from environment variable"""
    try:
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        return conn
    except Exception as e:
        utils.log(f"Database connection failed: {e}", 'error')
        return None


def initialize_login_activity_table():
    """Create login_activity table if it doesn't exist"""
    conn = get_db_connection()
    if conn is None:
        return False

    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS login_activity (
                id SERIAL PRIMARY KEY,
                login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                logout_time TIMESTAMP,
                session_id VARCHAR(255),
                device_info VARCHAR(500),
                ip_address VARCHAR(45)
            );
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_login_time ON login_activity(login_time DESC);
        """)
        conn.commit()
        cursor.close()
        conn.close()
        utils.log("login_activity table initialized", 'system')
        return True
    except Exception as e:
        utils.log(f"Failed to initialize login_activity table: {e}", 'error')
        return False


# ----------------------------------------------------------------------
def validate_table_name(func):
    def wrapper(self, table_name, *args, **kwargs):
        if table_name not in ["CardTransactions", "BankTransactions"]:
            utils.log(f"TableName must be either 'CardTransactions' or 'BankTransactions', got '{TableName}'", "error")
            return None  # or return an empty DataFrame, or raise Exception as needed
        return func(self, table_name, *args, **kwargs)
    return wrapper
# ----------------------------------------------------------------------
def check_for_empty_df(func):
    """Decorator for database functions.

    - If the wrapped function returns a pandas.DataFrame and it's empty, log a warning.
    - If the wrapped function returns a Warning instance or a string containing 'warning', log it.
    """
    def wrapper(*args, **kwargs):
        res = func(*args, **kwargs)
        try:
            # pandas DataFrame empty check
            if isinstance(res, pd.DataFrame):
                if res.empty:
                    utils.log(f"Query returned an empty DataFrame for function '{func.__name__}'", "warning")

        except Exception as e:
            utils.log(f"operator decorator processing error: {e}", "error")

        return res

    return wrapper
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------

class DataBase:

    __instance = None
    __lock = threading.Lock()
    connection: sqlite3.Connection
    cursor: sqlite3.Cursor

    def __new__(cls):
        with cls.__lock:
            if cls.__instance is None:
                cls.__instance = super().__new__(cls)

                # All queries use SQLite syntax (?), so always use SQLite.
                # On Vercel /var/task is read-only — use /tmp to match WebApp.py's _DB_PATH.
                db_path = '/tmp/ShmuelFamiliy.db' if os.getenv('DATABASE_URL') else f'{Paths.DB_NAME}.db'
                cls.__instance.connection = sqlite3.connect(db_path, check_same_thread=False)
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
                    );""")
                cls.__instance.cursor.execute("""
                    CREATE TABLE IF NOT EXISTS CashTransactions (
                    ID                  INTEGER         PRIMARY KEY ,
                    Name                CHAR            NOT NULL    ,
                    Execution_Date      DATE            NOT NULL    ,
                    Amount              INT             NOT NULL    ,
                    Currency            CHAR            NOT NULL    ,
                    Category            CHAR            NOT NULL    ,
                    Insertion_Date      DATE            NOT NULL    ,
                    Description         CHAR
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
                    Reserved            INT
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
                    Reserved            INT
                    );""")
                cls.__instance.cursor.execute("""
                    CREATE TABLE IF NOT EXISTS GymParticipants (
                    id              INTEGER     PRIMARY KEY AUTOINCREMENT,
                    name            TEXT        NOT NULL,
                    is_active       INTEGER     DEFAULT 1,
                    insertion_date  TEXT        NOT NULL
                    );""")
                cls.__instance.cursor.execute("""
                    CREATE TABLE IF NOT EXISTS GymSessions (
                    id              INTEGER     PRIMARY KEY AUTOINCREMENT,
                    date            TEXT        NOT NULL,
                    product_price   REAL        NOT NULL,
                    payer_id        INTEGER     NOT NULL    REFERENCES GymParticipants(id),
                    notes           TEXT,
                    insertion_date  TEXT        NOT NULL
                    );""")
                cls.__instance.cursor.execute("""
                    CREATE TABLE IF NOT EXISTS GymSessionParticipants (
                    session_id      INTEGER     REFERENCES GymSessions(id),
                    participant_id  INTEGER     REFERENCES GymParticipants(id),
                    PRIMARY KEY(session_id, participant_id)
                    );""")
                cls.__instance.cursor.execute("""
                    CREATE TABLE IF NOT EXISTS OtherAccountStatus (
                    ID              INTEGER     PRIMARY KEY AUTOINCREMENT,
                    AccountName     TEXT        NOT NULL,
                    StatusDate      DATE        NOT NULL,
                    Value           REAL        NOT NULL,
                    TransactionID   INTEGER,
                    FOREIGN KEY(TransactionID) REFERENCES BankTransactions(ID)
                    );""")
                cls.__instance.connection.commit()

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
        last_update = utils.date_ready(datetime.now().strftime("%d-%m-%Y")).date()
        self.cursor.execute("""
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
        self.cursor.execute("""
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
   
    def is_file_exists_v2(self, file_format: str, card_number: str, date: datetime) -> bool:
        '''
        Returns True if a record with the input parameters exists in the File table,
        False otherwise.
        '''
        ans = self.cursor.execute("""
                    SELECT 1
                    FROM File
                    WHERE Format = ?
                    AND Card_Number = ?
                    AND Date = ?;
                """, (file_format, card_number, date,)).fetchone()

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

    def get_housing_income(self, category: str) -> pd.DataFrame:
        """
        Return all Income (rent) entries for *category* across all time.
        Returns columns: Date, Name, Income.
        """
        data = self.cursor.execute("""
            SELECT Date, Name, Income
            FROM BankTransactions
            WHERE Category = ?
              AND Income > 0
            ORDER BY Date
        """, (category,)).fetchall()
        return pd.DataFrame(data, columns=["Date", "Name", "Income"])

    def get_all_category_transactions(self, category: str) -> pd.DataFrame:
        """
        Return all transactions (Out and Income) for *category* sorted by date descending.
        Mirrors the category-analysis path: fetch all → apply_splits → filter by category →
        process_prices on cards, so split children are included and values match exactly.
        Returns columns: Date, Name, Out, Income.
        """
        from src_utils.calculations import SimpleMath
        from datetime import datetime as _dt

        bank_raw = self.get_transactions('BankTransactions', category_filter=None, name_filter=None)
        bank_raw = self.apply_splits_to_df(bank_raw)
        bank_raw = bank_raw[bank_raw['Category'] == category].reset_index(drop=True)

        card_raw = self.get_transactions('CardTransactions', category_filter=None, name_filter=None)
        card_raw = self.apply_splits_to_df(card_raw)
        card_raw = card_raw[card_raw['Category'] == category].reset_index(drop=True)

        bank_df = pd.DataFrame({
            "Date":        bank_raw["Date"],
            "Name":        bank_raw["Name"],
            "Out":         bank_raw["Out"],
            "Income":      bank_raw["Income"],
            "Description": bank_raw["Description"] if "Description" in bank_raw.columns else "",
        }) if not bank_raw.empty else pd.DataFrame(columns=["Date", "Name", "Out", "Income", "Description"])

        if not card_raw.empty:
            card_proc = SimpleMath.process_prices(card_raw, date=_dt.now(), general_analysis=False)
            card_result = pd.DataFrame({
                "Date":        card_proc["Executed_Date"],
                "Name":        card_proc["Name"],
                "Out":         card_proc["Final_Value"].apply(lambda v: abs(float(v)) if v < 0 else 0.0),
                "Income":      card_proc["Final_Value"].apply(lambda v: float(v) if v > 0 else 0.0),
                "Description": card_proc["Description"] if "Description" in card_proc.columns else "",
            })
            combined = pd.concat([bank_df, card_result], ignore_index=True)
        else:
            combined = bank_df

        combined["Date"] = pd.to_datetime(combined["Date"])
        return combined.sort_values("Date", ascending=False).reset_index(drop=True)

    def get_housing_spending(self, category: str) -> pd.DataFrame:
        """
        Return all Out (spending) entries for *category* across all time.
        Mirrors the category-analysis path: fetch all → apply_splits → filter by category →
        process_prices on cards, so split children are included and values match exactly.
        Returns columns: Date, Name, Out.
        """
        from src_utils.calculations import SimpleMath
        from datetime import datetime as _dt

        bank_raw = self.get_transactions('BankTransactions', category_filter=None, name_filter=None)
        bank_raw = self.apply_splits_to_df(bank_raw)
        bank_raw = bank_raw[(bank_raw['Category'] == category) & (bank_raw['Out'] > 0)].reset_index(drop=True)

        card_raw = self.get_transactions('CardTransactions', category_filter=None, name_filter=None)
        card_raw = self.apply_splits_to_df(card_raw)
        card_raw = card_raw[card_raw['Category'] == category].reset_index(drop=True)

        bank_df = pd.DataFrame({
            "Date": bank_raw["Date"],
            "Name": bank_raw["Name"],
            "Out":  bank_raw["Out"],
        }) if not bank_raw.empty else pd.DataFrame(columns=["Date", "Name", "Out"])

        if not card_raw.empty:
            card_proc = SimpleMath.process_prices(card_raw, date=_dt.now(), general_analysis=False)
            spending = card_proc[card_proc["Final_Value"] < 0].copy()
            card_result = pd.DataFrame({
                "Date": spending["Executed_Date"],
                "Name": spending["Name"],
                "Out":  spending["Final_Value"].apply(lambda v: abs(float(v))),
            })
            combined = pd.concat([bank_df, card_result], ignore_index=True)
        else:
            combined = bank_df

        combined["Date"] = pd.to_datetime(combined["Date"])
        return combined.sort_values("Date").reset_index(drop=True)

    def get_mortgage_payments(self, category: str, name_keyword: str) -> pd.DataFrame:
        """
        Return all bank transactions whose Name contains *name_keyword*
        and whose Category matches *category*, across all time.
        Used to fetch actual historic mortgage payments.
        Returns columns: Date, Name, Amount (positive = money out).
        """
        data = self.cursor.execute("""
            SELECT Date, Name, Out AS Amount
            FROM BankTransactions
            WHERE Category = ?
              AND Name LIKE ?
              AND Out > 0
            ORDER BY Date
        """, (category, f"%{name_keyword}%")).fetchall()
        return pd.DataFrame(data, columns=["Date", "Name", "Amount"])

    def get_transactions_by_category(self, cat_name: str) -> pd.DataFrame:
        """
        Get all transactions by category name from both CardTrasactions and BankTransactions tables.
        Transactions format is:
        """
        data = self.cursor.execute("""
                                   SELECT
                                        'BankTransactions' AS TableName,
                                        ID,
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
                                        ID,
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
                                   (cat_name, cat_name)).fetchall()
    
        return pd.DataFrame(data, columns=[d[0] for d in self.cursor.description])

    def get_monthly_earnings(self, year: int, month: int, category=None, name=None) -> pd.DataFrame:
        """
        The function receives a year, a month, a category name and a business name
        and returns all the Spending transactions associated with the given categories and/or bussiness
        in the given date in the same month only. 
        If category is None, transaction will not be filtered by category.
        If business name is None, transaction will not be filtered by category.
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

        if name is not None:
            df = df[df['Name'] == name]

        return df

    def get_monthly_spendings(self, year: int, month: int, category=None, name=None) -> pd.DataFrame:
        """
        The function receives a year, a month, a category name and a business name.
        and returns all the Earnings transactions associated with the given categories and or business name
        in the given date in the same month only. 
        If category is None, transaction will not be filtered by category.
        If business name is None, transaction will not be filtered by category.
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
        current_month = '0' + str(month) if len(str(month)) == 1 else str(month)
        next_year = f"{utils.next_month(datetime(year, month, 1)).year}"
        
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
                                        ID,
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
                                        ID,
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
                                        (strftime('%m', Charge_Date) = ? and strftime('%Y', Charge_Date) = ?)
                                        OR
                                        (strftime('%m', Charge_Date) = ? and strftime('%Y', Charge_Date) = ?)
                                    )
                                    """, (b_init, b_end, "אשראי", b_init, b_end, next_month, next_year, current_month, year,)).fetchall()
        df = pd.DataFrame(data, columns=[d[0] for d in self.cursor.description])
        if category is not None:
            df = df[df['Category'] == category]
        
        if name is not None:
            df = df[df['Name'] == name]
        
        return df

    # Query NOTE: Executed_Date > 0 (In the CardTransaction table) represents only Negative transaction since Negative transactions
    # appears with a positive value in the Card table.

    def get_earnings(self, category=None) -> pd.DataFrame:
        """
        The function receives a category and returns all earnings transactions that are associated with this category.
        If category argument is None - all spending trasnactions will be returned.
        the dataframed format fits the process_prices function.
        """
        if not (isinstance(category, str) or category is None):
            utils.log("Argument input error in 'get_spendings'", "error")

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
                                    WHERE 
                                            Income != 0
                                        AND Category != ? 
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
                                    WHERE 
                                        Charge_Value < 0
                                    """, ("אשראי", )).fetchall()
        
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
                                        Charge_Value > 0 
                                        """, ("אשראי", )).fetchall()      
        df = pd.DataFrame(data, columns=[d[0] for d in self.cursor.description])
        if category is not None:
            df = df[df['Category'] == category]

        return df  

    @check_for_empty_df
    def get_transactions(self, table: Literal['BankTransactions', 'CardTransactions'],
                                        category_filter: Optional[str],
                                        name_filter: Optional[str]) -> pd.DataFrame:
        """
        get all transactions from the given table that fit the given filters.
        function is process_proces ready.

        Args:
            table (Literal['BankTransactions', 'CardTransactions']): the table to query from.
            category_filter (Optional[str]): if not None, filter by this category.
            name_filter (Optional[str]): if not None, filter by this business name.
        Returns:
            pd.DataFrame: dataframe of the queried transactions.
        """

        if table not in ['BankTransactions', 'CardTransactions']:
            utils.log(f"Bad input {table} in 'get_all_bank_transactions' in DataBase class", "error")

        query = f"""
                SELECT *, '{table}' AS TableName
                FROM {table}
                """ 
        query_values = [] 
        query_parts = []

        if not ((category_filter is None or category_filter == "") and 
                (name_filter is None or name_filter == "")):
            query += "WHERE "

        if category_filter is not None and category_filter != "":
            query_parts.append("category = ?")
            query_values.append(category_filter)

        if name_filter is not None and name_filter != "":
            query_parts.append("name = ?")
            query_values.append(name_filter)

        query += " AND ".join(query_parts)
        return pd.DataFrame(self.cursor.execute(query, query_values).fetchall(),
                            columns=[d[0] for d in self.cursor.description])
        
    # def get_transactions(self, category=None, business=None):
    #     """
    #     get all transactions that fit the given filters.
    #     function is process_proces ready.
    #     """
    #     if not (isinstance(category, str) or category is None):
    #         utils.log("Argument input 'category' error in 'get_transactions'", "error")
        
    #     if not (isinstance(business, str) or business is None):
    #         utils.log("Argument input 'business' error in 'get_transactions'", "error")

    #     data = self.cursor.execute("""
    #                                 SELECT
    #                                     'BankTransactions' AS TableName,
    #                                     Ref AS 'Ref/CardID',
    #                                     Name,
    #                                     Date AS 'Date/Executed_Date',
    #                                     Value_Date AS 'Value_Date/Charge_Date',
    #                                     Out AS 'Out/Transaction_value',
    #                                     Income AS 'Income/Charge_Value',
    #                                     Description AS 'Description/Charge_Currency',
    #                                     Reserved AS 'Reserved/Value_Currency',
    #                                     Category,
    #                                     Extra_Info,
    #                                     Source_file,
    #                                     Description
    #                                 FROM BankTransactions
    #                                 WHERE Category != ?
    #                                 UNION ALL
    #                                 SELECT
    #                                     'CardTransactions' AS TableName,
    #                                     CardID,
    #                                     Name,
    #                                     Executed_Date,
    #                                     Charge_Date,
    #                                     Transaction_Value,
    #                                     Charge_Value,
    #                                     Charge_Currency,
    #                                     Value_Currency,
    #                                     Category,
    #                                     Extra_Info,
    #                                     Source_file,
    #                                     Description
    #                                 FROM CardTransactions
    #                                     """, ("אשראי", )).fetchall()  
    #     df = pd.DataFrame(data, columns=[d[0] for d in self.cursor.description])
        
    #     if category is not None:
    #         df = df[df['Category'] == category]
        
    #     if business is not None:
    #         df = df[df['Name'] == business]

    #     return df

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
        Remove the entries associated with the file name from the db.
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

    def get_untagged(self, table: str = None) -> Tuple[list, list]:
        """
        Get all untagged items in database.
        An untagged item is a transaction with no category.
        If table is specified as 'BankTransactions' or 'CardTransactions', only return untagged entries from that table.
        Otherwise, return both as before.
        """
        valid_tables = [None, "BankTransactions", "CardTransactions"]
        if table not in valid_tables:
            from src_utils.utils import utils
            utils.log(f"Invalid table argument '{table}' in get_untagged. Must be one of {valid_tables}.", "error")

        if table == "BankTransactions":
            res = self.cursor.execute("""
                                    SELECT
                                        'BankTransactions' as TableName,
                                        ID,
                                        Date,
                                        Name,
                                        Ref,
                                        Out,
                                        Income,
                                        Extra_Info,
                                        Source_file,
                                        Null
                                    FROM BankTransactions
                                    WHERE Category IS 'NotCategorized'
                                    ORDER BY ID DESC
                                """).fetchall()
            return res, [d[0] for d in self.cursor.description]
        elif table == "CardTransactions":
            res = self.cursor.execute("""
                                    SELECT
                                        'CardTransactions' AS TableName,
                                        ID,
                                        Executed_Date,
                                        Name,
                                        CardID AS 'CardID/Ref',
                                        Charge_Value AS 'Charge_Value/Out',
                                        Transaction_Value AS 'Transaction_Value/Income' ,
                                        Extra_Info,
                                        Source_file,
                                        Charge_Currency
                                    FROM CardTransactions
                                    WHERE Category IS 'NotCategorized'
                                    ORDER BY ID DESC
                                """).fetchall()
            return res, [d[0] for d in self.cursor.description]
        else:
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
                                        Source_file,
                                        Null
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
                                        Source_file,
                                        Charge_Currency
                                    FROM CardTransactions
                                    WHERE Category IS 'NotCategorized'
                                    ORDER BY ID DESC
                                """).fetchall()
            # Sortion order is made for better handling of tagging
            # x[2] is the location of the Date
            sorted_list = sorted(res1 + res2, key=lambda x: x[2], reverse=True)
            return sorted_list, [d[0] for d in self.cursor.description]

    def get_untagged_card_payments(self) -> Tuple[list, list]:
        """
        Get all untagged CardTransactions with all necessary columns.
        Returns: (list of tuples, list of column names)
        """
        res = self.cursor.execute("""
            SELECT
                ID,
                Name,
                Charge_Date,
                Charge_Value,
                Extra_Info,
                Category,
                Description
            FROM CardTransactions
            WHERE Category IS 'NotCategorized'
            ORDER BY Charge_Date ASC
        """).fetchall()
        return res, [d[0] for d in self.cursor.description]

    @validate_table_name
    def set_category(self, table_name: str, id: int, category: str):
        """
        Set a tag for a transaction with a given id.
        """
        match table_name:
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
                utils.log(f"Bad input {table_name} in 'set_category' in DataBase class", "error")

    @validate_table_name
    def set_category_ui(self, table_name: str, id: int, category: str, is_auto: bool = False):
        """
        Set a tag for a transaction via the UI.
        Reserved = 0 for manual tag, 1 for auto tag.
        """
        reserved_val = 1 if is_auto else 0
        match table_name:
            case "CardTransactions":
                self.cursor.execute("""
                                    UPDATE CardTransactions
                                    SET Category = ?, Reserved = ?
                                    WHERE ID = ?
                                    """, (category, reserved_val, id,))
                self.connection.commit()
            case "BankTransactions":
                self.cursor.execute("""
                                    UPDATE BankTransactions
                                    SET Category = ?, Reserved = ?
                                    WHERE ID = ?
                                    """, (category, reserved_val, id,))
                self.connection.commit()
            case _:
                utils.log(f"Bad input {table_name} in 'set_category_ui' in DataBase class", "error")

    def get_untagged_recent(self, limit: int = 30) -> list:
        """
        Get the most recent untagged transactions from both tables.
        Returns a list of dicts with keys: table_name, id, name, exec_date, charge_date,
        transaction_value, charge_value, currency, reserved, card_id.
        """
        rows = self.cursor.execute("""
            SELECT
                'CardTransactions' AS table_name,
                ID,
                Name,
                Executed_Date AS exec_date,
                Charge_Date   AS charge_date,
                Transaction_Value AS transaction_value,
                Charge_Value      AS charge_value,
                Charge_Currency   AS currency,
                Value_Currency    AS value_currency,
                Reserved,
                CardID            AS card_id
            FROM CardTransactions
            WHERE Category IS 'NotCategorized'
              AND NOT EXISTS (
                SELECT 1 FROM TransactionSplits
                WHERE Original_Table = 'CardTransactions' AND Original_ID = CardTransactions.ID
              )
            UNION ALL
            SELECT
                'BankTransactions' AS table_name,
                ID,
                Name,
                Date       AS exec_date,
                Value_Date AS charge_date,
                Income     AS transaction_value,
                Out        AS charge_value,
                'ILS'      AS currency,
                'ILS'      AS value_currency,
                Reserved,
                NULL       AS card_id
            FROM BankTransactions
            WHERE Category IS 'NotCategorized'
              AND NOT EXISTS (
                SELECT 1 FROM TransactionSplits
                WHERE Original_Table = 'BankTransactions' AND Original_ID = BankTransactions.ID
              )
            ORDER BY exec_date DESC
            LIMIT ?
        """, (limit,)).fetchall()
        cols = ['table_name', 'id', 'name', 'exec_date', 'charge_date',
                'transaction_value', 'charge_value', 'currency', 'value_currency', 'reserved', 'card_id']
        return [dict(zip(cols, r)) for r in rows]

    def get_recently_tagged(self, limit: int = 30) -> list:
        """
        Get recently tagged transactions (Category != NotCategorized) from both tables.
        Returns list of dicts including the category and reserved flag (0=manual, 1=auto).
        """
        rows = self.cursor.execute("""
            SELECT
                'CardTransactions' AS table_name,
                ID,
                Name,
                Executed_Date AS exec_date,
                Charge_Date   AS charge_date,
                Transaction_Value AS transaction_value,
                Charge_Value      AS charge_value,
                Charge_Currency   AS currency,
                Value_Currency    AS value_currency,
                Category,
                Reserved
            FROM CardTransactions
            WHERE Category IS NOT 'NotCategorized'
            UNION ALL
            SELECT
                'BankTransactions' AS table_name,
                ID,
                Name,
                Date       AS exec_date,
                Value_Date AS charge_date,
                Income     AS transaction_value,
                Out        AS charge_value,
                'ILS'      AS currency,
                'ILS'      AS value_currency,
                Category,
                Reserved
            FROM BankTransactions
            WHERE Category IS NOT 'NotCategorized'
            ORDER BY exec_date DESC
            LIMIT ?
        """, (limit,)).fetchall()
        cols = ['table_name', 'id', 'name', 'exec_date', 'charge_date',
                'transaction_value', 'charge_value', 'currency', 'value_currency', 'category', 'reserved']
        return [dict(zip(cols, r)) for r in rows]

    def get_high_value_untagged(self, threshold: float = 500.0) -> list:
        """
        Get untagged transactions with charge_value above threshold.
        Returns list of dicts, sorted by value descending.
        """
        rows = self.cursor.execute("""
            SELECT
                'CardTransactions' AS table_name,
                ID,
                Name,
                Executed_Date AS exec_date,
                Charge_Date   AS charge_date,
                Transaction_Value AS transaction_value,
                Charge_Value      AS charge_value,
                Charge_Currency   AS currency,
                Value_Currency    AS value_currency,
                Reserved,
                CardID            AS card_id
            FROM CardTransactions
            WHERE Category IS 'NotCategorized'
              AND Charge_Value >= ?
              AND NOT EXISTS (
                SELECT 1 FROM TransactionSplits
                WHERE Original_Table = 'CardTransactions' AND Original_ID = CardTransactions.ID
              )
            UNION ALL
            SELECT
                'BankTransactions' AS table_name,
                ID,
                Name,
                Date       AS exec_date,
                Value_Date AS charge_date,
                Income     AS transaction_value,
                Out        AS charge_value,
                'ILS'      AS currency,
                'ILS'      AS value_currency,
                Reserved,
                NULL       AS card_id
            FROM BankTransactions
            WHERE Category IS 'NotCategorized'
              AND (Out >= ? OR Income >= ?)
              AND NOT EXISTS (
                SELECT 1 FROM TransactionSplits
                WHERE Original_Table = 'BankTransactions' AND Original_ID = BankTransactions.ID
              )
            ORDER BY charge_value DESC
        """, (threshold, threshold, threshold)).fetchall()
        cols = ['table_name', 'id', 'name', 'exec_date', 'charge_date',
                'transaction_value', 'charge_value', 'currency', 'value_currency', 'reserved', 'card_id']
        return [dict(zip(cols, r)) for r in rows]

    def count_untagged_total(self) -> int:
        """Return total count of untagged transactions across both tables."""
        result = self.cursor.execute("""
            SELECT COUNT(*) FROM (
                SELECT ID FROM CardTransactions
                WHERE Category IS 'NotCategorized'
                  AND NOT EXISTS (
                    SELECT 1 FROM TransactionSplits
                    WHERE Original_Table = 'CardTransactions' AND Original_ID = CardTransactions.ID
                  )
                UNION ALL
                SELECT ID FROM BankTransactions
                WHERE Category IS 'NotCategorized'
                  AND NOT EXISTS (
                    SELECT 1 FROM TransactionSplits
                    WHERE Original_Table = 'BankTransactions' AND Original_ID = BankTransactions.ID
                  )
            )
        """).fetchone()
        return result[0] if result else 0

    def count_category_usages(self) -> dict:
        """
        Returns a dict of {category: count} for all non-NotCategorized transactions.
        """
        rows = self.cursor.execute("""
            SELECT Category, COUNT(*) FROM (
                SELECT Category FROM CardTransactions WHERE Category IS NOT 'NotCategorized'
                UNION ALL
                SELECT Category FROM BankTransactions WHERE Category IS NOT 'NotCategorized'
            ) GROUP BY Category ORDER BY COUNT(*) DESC
        """).fetchall()
        return {r[0]: r[1] for r in rows}

    def count_auto_tagged_per_name(self) -> dict:
        """Returns {name: count} for all tagged (non-NotCategorized) transactions across both tables."""
        rows = self.cursor.execute("""
            SELECT Name, COUNT(*) FROM (
                SELECT Name FROM CardTransactions WHERE Category IS NOT 'NotCategorized'
                UNION ALL
                SELECT Name FROM BankTransactions WHERE Category IS NOT 'NotCategorized'
            ) GROUP BY Name
        """).fetchall()
        return {r[0]: r[1] for r in rows}

    def remap_auto_tagged(self, name: str, new_category: str) -> int:
        """Update ALL existing transactions matching name to new_category (auto + manual).
        Returns total rows updated."""
        self.cursor.execute(
            "UPDATE CardTransactions SET Category = ? WHERE Name = ?",
            (new_category, name)
        )
        card_count = self.cursor.rowcount
        self.cursor.execute(
            "UPDATE BankTransactions SET Category = ? WHERE Name = ?",
            (new_category, name)
        )
        bank_count = self.cursor.rowcount
        self.connection.commit()
        return card_count + bank_count

    def search_tagged(self, query: str, limit: int = 50) -> list:
        """Search tagged transactions by name (partial) or exact numeric ID."""
        try:
            id_val = int(query)
            rows = self.cursor.execute("""
                SELECT 'CardTransactions' AS table_name, ID, Name,
                    Executed_Date AS exec_date, Charge_Date AS charge_date,
                    Transaction_Value AS transaction_value, Charge_Value AS charge_value,
                    Charge_Currency AS currency, Category, Reserved, CardID AS card_id,
                    COALESCE(Description, '') AS description
                FROM CardTransactions WHERE Category IS NOT 'NotCategorized' AND ID = ?
                UNION ALL
                SELECT 'BankTransactions' AS table_name, ID, Name,
                    Date AS exec_date, Value_Date AS charge_date,
                    Income AS transaction_value, Out AS charge_value,
                    'ILS' AS currency, Category, Reserved, NULL AS card_id,
                    COALESCE(Description, '') AS description
                FROM BankTransactions WHERE Category IS NOT 'NotCategorized' AND ID = ?
                ORDER BY exec_date DESC LIMIT ?
            """, (id_val, id_val, limit)).fetchall()
        except ValueError:
            like = f'%{query}%'
            rows = self.cursor.execute("""
                SELECT 'CardTransactions' AS table_name, ID, Name,
                    Executed_Date AS exec_date, Charge_Date AS charge_date,
                    Transaction_Value AS transaction_value, Charge_Value AS charge_value,
                    Charge_Currency AS currency, Category, Reserved, CardID AS card_id,
                    COALESCE(Description, '') AS description
                FROM CardTransactions WHERE Category IS NOT 'NotCategorized' AND Name LIKE ?
                UNION ALL
                SELECT 'BankTransactions' AS table_name, ID, Name,
                    Date AS exec_date, Value_Date AS charge_date,
                    Income AS transaction_value, Out AS charge_value,
                    'ILS' AS currency, Category, Reserved, NULL AS card_id,
                    COALESCE(Description, '') AS description
                FROM BankTransactions WHERE Category IS NOT 'NotCategorized' AND Name LIKE ?
                ORDER BY exec_date DESC LIMIT ?
            """, (like, like, limit)).fetchall()
        cols = ['table_name', 'id', 'name', 'exec_date', 'charge_date',
                'transaction_value', 'charge_value', 'currency', 'category', 'reserved', 'card_id',
                'description']
        return [dict(zip(cols, r)) for r in rows]

    @validate_table_name
    def set_description(self, table_name: str, id: int, description: str):
        """
        Set a description for a transaction with a given id.
        """
        query = """
                    UPDATE {}
                    SET Description = ?
                    WHERE ID = ?
                """.format(table_name)
        
        self.cursor.execute(query, (description, id))

    def get_transactions_by_name(self, table_name: str, name: str) -> pd.DataFrame:
        """
        Get All transactions from the given table that has the same exact name.
        """
        query = """
                    SELECT *
                    FROM {}
                    WHERE Name = ?
                """.format(table_name)
        return pd.DataFrame(self.cursor.execute(query, (name,)).fetchall(), columns=[d[0] for d in self.cursor.description])

    @validate_table_name
    def get_by_name_uncategorized(self, table_name: str, name: str) -> pd.DataFrame:
        """
        WARNING - The function only returns transactions with no category.
        Get All transactions from the given table that has the same exact name.
        """
        query = """
                    SELECT *
                    FROM {}
                    WHERE Name = ?
                    AND Category IS 'NotCategorized'
                    """.format(table_name)
        return pd.DataFrame(self.cursor.execute(query, (name,)).fetchall(), columns=[d[0] for d in self.cursor.description])

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

    def card_sum(self, date: datetime) -> pd.DataFrame:
        """
        The function Receives a datetime object and returns a dataframe object.
        The data frame will include card types transactions from all cards in the database
        which were exectued in the month of the given date.
        The function was written particularly for the card verification feature.
        """
        m_i = '0' + str(date.month) if len(str(date.month)) == 1 else str(date.month)
        y_i = str(date.year)
        m_ip1, y_ip1 = utils.next_month(date).month, str(utils.next_month(date).year)
        m_im1, y_im1 = utils.previous_month(date).month, str(utils.previous_month(date).year)
        # y_i might be equal to y_ip1
        m_ip1 = '0' + str(m_ip1) if len(str(m_ip1)) == 1 else str(m_ip1)
        m_im1 = '0' + str(m_im1) if len(str(m_im1)) == 1 else str(m_im1)

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
                                   Transaction_Value AS 'Out/Transaction_value',
                                   Category
                            FROM CardTransactions
                            WHERE ( 
                                    (strftime('%m', Executed_Date) = ? AND strftime('%m', Charge_Date) = ?) 
                                    OR 
                                    (strftime('%m', Executed_Date) = ? AND strftime('%m', Charge_Date) = ? AND Transaction_Value > 0)
                                    OR
                                   (strftime('%m', Executed_Date) = ? AND strftime('%m', Charge_Date) = ?)
                                   ) 
                                   AND 
                                   strftime('%Y', Charge_Date) = ?

                            """, (m_i, m_ip1, m_ip1, m_ip1, m_im1, m_ip1, y_ip1, )).fetchall() # TODO can this be simplified for just the transactions at the set charge date?
        
        return pd.DataFrame(data, columns=[d[0] for d in self.cursor.description])

    def get_Bank_Transactions(self, month: int, year: int):
        """
        Get all bank transactions of month @month and year @year,
        day is not relevant.
        """
        str_month = str(month)
        if len(str_month) == 1:
            str_month = '0' + str_month

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
        Returns the total sum of all spendings of a chosen category or business transactions
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
        return pd.DataFrame(data=data, columns=[d[0] for d in self.cursor.description])

    def query_Bank_Transactions_for_validation(self, last_valid_date: datetime) -> pd.DataFrame:
        """
        TODO
        """
        last_valid_date_str = last_valid_date.strftime('%Y-%m-%d %H:%M:%S')
    
        query = """
                    SELECT ID, Date, Out, Income, Balance
                    FROM BankTransactions
                    WHERE (Date >= ?)
                """
        data = self.cursor.execute(query, (last_valid_date_str,)).fetchall()
        return pd.DataFrame(data=data, columns=[d[0] for d in self.cursor.description])

    def query_by_substring(self, input_str: str) -> pd.DataFrame:
        """
        
        """
        query = """
        SELECT *
        FROM CardTransactions 
        WHERE Name LIKE ? or Description Like ?

        """

        x = '%' + input_str + '%'
        data = self.cursor.execute(query, (x,x,)).fetchall()
        return pd.DataFrame(data=data, columns=[d[0] for d in self.cursor.description])
    
    def get_all_transactions_since(self, date: datetime) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        The function receives a date
        and returns all the transactions (spendings and incomes) from the given date.
        """
        date_str = date.strftime('%Y-%m-%d')

        data_1 = self.cursor.execute("""
                            SELECT *, 'BankTransactions' AS TableName                                
                            FROM BankTransactions
                            WHERE Date >= ?           
                            """, (date_str,)).fetchall()
        
        df_1 = pd.DataFrame(data=data_1, columns=[d[0] for d in self.cursor.description])
        
        data_2 = self.cursor.execute("""
                            SELECT *, 'CardTransactions' AS TableName                               
                            FROM CardTransactions
                            WHERE Executed_Date >= ?
                            """, (date_str,)).fetchall()
    
        df_2 = pd.DataFrame(data=data_2, columns=[d[0] for d in self.cursor.description])

        # Rename columns if necessary to make them consistent (for example, Date and Executed_Date)
        df_2.rename(columns={'Executed_Date': 'Date'}, inplace=True)  # Make column names consistent

        return df_1, df_2
    
    def create_other_account_table(self):
        """Creates or updates the other accounts status table"""
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS OtherAccountStatus (
                ID              INTEGER     PRIMARY KEY AUTOINCREMENT,
                AccountName     TEXT        NOT NULL,
                StatusDate      DATE        NOT NULL,
                Value          REAL        NOT NULL,
                TransactionID  INTEGER,
                FOREIGN KEY(TransactionID) REFERENCES BankTransactions(ID)
            );
        """)
        self.connection.commit()

    def insert_other_account_status(self, account_name: str, status_date: str, value: float, transaction_id: int = None):
        """Insert a new status record for another account"""
        query = """
            INSERT INTO OtherAccountStatus (AccountName, StatusDate, Value, TransactionID)
            VALUES (?, ?, ?, ?)
        """
        self.cursor.execute(query, (account_name, status_date, value, transaction_id))
        self.connection.commit()

    def get_account_entries_with_dates(self, account_name: str = None, from_date: datetime = None) -> pd.DataFrame:
        """
        Get historical values for one or all other accounts after a given date.
        
        Args:
            account_name (str, optional): If provided, get data only for this account.
                                        If None, get data for all accounts.
            from_date (datetime, optional): Only get entries after this date.
                                          If None, defaults to 1 year ago.
        Returns:
            pd.DataFrame: DataFrame with columns ['Date', 'Value', 'AccountName'] 
                         containing the account history from the given date.
        """
        # Default to 1 year ago if no date provided
        if from_date is None:
            from_date = datetime.now() - pd.DateOffset(years=1)
        
        # Convert date to string format SQLite understands
        from_date_str = from_date.strftime('%Y-%m-%d')

        # Base query with date filter
        query = """
            SELECT
                StatusDate as Date,
                Value,
                AccountName,
                COALESCE(Currency, 'ILS') as Currency
            FROM OtherAccountStatus
            WHERE StatusDate >= ?
            {}
            ORDER BY StatusDate ASC
        """

        if account_name:
            where_clause = "AND AccountName = ?"
            data = self.cursor.execute(query.format(where_clause),
                                     (from_date_str, account_name)).fetchall()
        else:
            data = self.cursor.execute(query.format(""),
                                     (from_date_str,)).fetchall()

        df = pd.DataFrame(data, columns=['Date', 'Value', 'AccountName', 'Currency'])
        df['Date'] = pd.to_datetime(df['Date'])
        return df

    def get_all_account_names(self) -> list[str]:
        """
        Get list of all accounts from OtherAccountStatus table
        
        Returns:
            list[str]: List of unique account names
        """
        query = "SELECT DISTINCT AccountName FROM OtherAccountStatus"
        result = self.cursor.execute(query).fetchall()
        return [row[0] for row in result]

    def delete_account(self, account_name: str) -> bool:
        """
        Delete all records for a given account
        
        Args:
            account_name (str): Name of account to delete
            
        Returns:
            bool: True if successful, False if error occurred
        """
        try:
            self.cursor.execute(
                "DELETE FROM OtherAccountStatus WHERE AccountName = ?", 
                (account_name,)
            )
            self.connection.commit()
            return True
        except Exception as e:
            utils.log(f"Error deleting account: {str(e)}", "error")
            return False

    def get_account_entries(self) -> list:
        """
        Get all entries from OtherAccountStatus with their IDs
        
        Returns:
            list: List of tuples containing (ID, StatusDate, Value)
        """
        query = """
            SELECT ID, StatusDate, Value 
            FROM OtherAccountStatus 
            ORDER BY StatusDate DESC
        """
        return self.cursor.execute(query).fetchall()

    def delete_account_entry(self, entry_id: int) -> bool:
        """
        Delete a single entry from OtherAccountStatus by ID
        
        Args:
            entry_id (int): ID of entry to delete
            
        Returns:
            bool: True if successful, False if error occurred
        """
        try:
            self.cursor.execute(
                "DELETE FROM OtherAccountStatus WHERE ID = ?", 
                (entry_id,)
            )
            self.connection.commit()
            return True
        except Exception as e:
            utils.log(f"Error deleting entry: {str(e)}", "error")
            return False


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


    def reset_category_by_id(self) -> None:
        param1 = utils.template_menu(['Bank', 'Card'], msg='Choose the relevant table:')
        param2 = input('Insert transaction ID:')
        param3 = "NotCategorized"
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

    def replace_category(self, frm: str, to: str):
        """
        The function receives 2 categories, an existing category to change
        and another category (could be a new category or an existing one) to change to.
        the number of affected rows in each table is printed.
        """
        for table_name in ['BankTransactions', 'CardTransactions']:
            
            self.cursor.execute(f"""
                    UPDATE {table_name}
                    SET category = ?
                    WHERE category = ?
                """, (to, frm,))
            
            rows_affected = self.cursor.rowcount
            utils.log(f"Rows updated in {table_name}: {rows_affected}", 'system')
    
    def delete_transactions(self, ids: Tuple[list[str], str]):
        """
        The function will receive a single id or a list of id's of transaction from the
        Card transaction table.
        the function will delete the transaction and update the relevant file 'update time'.
        please note that currently there is no method to log deleted transactions except for the
        logger txt file.
        """
        ids = [ids] if not isinstance(ids, list) else ids   # In case more than 1 id was inserted
        last_update = datetime.now().strftime("%Y-%m-%d")
        for id in ids:
            query_info = """SELECT Source_file, CardID
                            From CardTransactions
                            WHERE ID = ?
                            """
            (file_name, card_id) = self.cursor.execute(query_info, (id,)).fetchone()
            
            query_del = """ DELETE 
                            FROM CardTransactions
                            WHERE Id = ?
                        """

            query_upd = """ UPDATE File
                            SET Last_update = ?
                            WHERE File_Name = ? AND Card_Number = ?
                        """
                            # SET Bad_rows = Bad_rows || ?
                            # WHERE some_condition;  # Modify this as per your condition
            self.cursor.execute(query_del, (id,))
            self.cursor.execute(query_upd, (last_update, file_name, card_id))
            utils.log(f"Transaction of ID ({id}) from file ({file_name}) [{card_id}] was deleted, Please commit the changes...")


    def insert_Cash_Transaction(self,
                                name: str, 
                                executed_date: datetime,
                                amount: float,
                                currency: str,
                                category: str = "NotCategorized",
                                description: str = "") -> bool:
        """
        The function will insert a cash transaction to the bank transactions table.
        """
        insertion_date = datetime.now()
        self.cursor.execute("""
                INSERT INTO CashTransactions (Name, Execution_Date, Amount, Currency, Category, insertion_date, Description)
                VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, executed_date, amount, currency, category, insertion_date, description))

        return True

# ----------------------------------------------------------------------
# ----------------------------------------------------------------------

    def commit_changes(self) -> None:
        self.connection.commit()

    def _ensure_pg_connection(self):
        """Ensure PostgreSQL connection is alive; reconnect if needed"""
        if self.connection is None:
            return False
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return True
        except Exception:
            return False

    # ── Login activity (PostgreSQL) ────────────────────────────────────────────

    def log_login(self, session_id, device_info, ip_address):
        """Log a user login event"""
        if not self._ensure_pg_connection():
            return False
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO login_activity (session_id, device_info, ip_address)
                VALUES (%s, %s, %s)
            """, (session_id, device_info, ip_address))
            self.connection.commit()
            cursor.close()
            return True
        except Exception as e:
            utils.log(f"Failed to log login: {e}", 'error')
            return False

    def log_logout(self, session_id):
        """Log a user logout event"""
        if not self._ensure_pg_connection():
            return False
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                UPDATE login_activity
                SET logout_time = CURRENT_TIMESTAMP
                WHERE session_id = %s AND logout_time IS NULL
            """, (session_id,))
            self.connection.commit()
            cursor.close()
            return True
        except Exception as e:
            utils.log(f"Failed to log logout: {e}", 'error')
            return False

    def get_login_activity(self):
        """Get all login activity (for activity log page)"""
        if not self._ensure_pg_connection():
            return []
        try:
            cursor = self.connection.cursor(cursor_factory=DictCursor)
            cursor.execute("""
                SELECT id, login_time, logout_time, device_info, ip_address
                FROM login_activity
                ORDER BY login_time DESC
            """)
            rows = cursor.fetchall()
            cursor.close()
            return rows
        except Exception as e:
            utils.log(f"Failed to get login activity: {e}", 'error')
            return []

    def get_monthly_bank_balances(self, from_date: datetime = None) -> pd.DataFrame:
        """
        Get end-of-month balances from BankTransactions after a given date.
        Filters out rows where Balance is NULL, empty string, or only whitespace.
        
        Args:
            from_date (datetime, optional): Only get entries after this date.
                                          If None, defaults to 1 year ago.
        Returns:
            pd.DataFrame: DataFrame with columns ['Date', 'Balance'] containing 
                         valid end-of-month balances
        """
        if from_date is None:
            from_date = datetime.now() - pd.DateOffset(years=1)
        
        from_date_str = from_date.strftime('%Y-%m-%d')

        query = """
            WITH MonthlyBalances AS (
                SELECT 
                    Date,
                    Balance,
                    strftime('%Y-%m', Date) as YearMonth,
                    ROW_NUMBER() OVER (
                        PARTITION BY strftime('%Y-%m', Date)
                        ORDER BY Date DESC, ID DESC
                    ) as rn
                FROM BankTransactions
                WHERE Date >= ?
                AND Balance IS NOT NULL 
                AND trim(Balance) != ''
                AND Balance != ' '
            )
            SELECT 
                Date,
                Balance
            FROM MonthlyBalances
            WHERE rn = 1
            ORDER BY Date ASC
        """
        
        data = self.cursor.execute(query, (from_date_str,)).fetchall()
        df = pd.DataFrame(data, columns=['Date', 'Balance'])
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.dropna(subset=['Balance'])
        # Convert Balance to numeric, removing any non-numeric entries
        df['Balance'] = pd.to_numeric(df['Balance'], errors='coerce')
        df = df.dropna(subset=['Balance'])
        return df

    def get_monthly_bank_balances(self, from_date: datetime = None) -> pd.DataFrame:
        """
        Get end-of-month balances from BankTransactions after a given date.
        Filters out rows where Balance is NULL, empty string, or only whitespace.
        
        Args:
            from_date (datetime, optional): Only get entries after this date.
                                          If None, defaults to 1 year ago.
        Returns:
            pd.DataFrame: DataFrame with columns ['Date', 'Balance'] containing 
                         valid end-of-month balances
        """
        # Default to 1 year ago if no date provided 
        if from_date is None:
            from_date = datetime.now() - pd.DateOffset(years=1)
        
        # Convert date to string format SQLite understands
        from_date_str = from_date.strftime('%Y-%m-%d')

        query = """
            WITH MonthlyBalances AS (
                SELECT 
                    Date,
                    Balance,
                    strftime('%Y-%m', Date) as YearMonth,
                    ROW_NUMBER() OVER (
                        PARTITION BY strftime('%Y-%m', Date)
                        ORDER BY Date DESC, ID DESC
                    ) as rn
                FROM BankTransactions
                WHERE Date >= ?
                AND Balance IS NOT NULL 
                AND trim(Balance) != ''
                AND Balance != ' '
            )
            SELECT 
                Date,
                Balance
            FROM MonthlyBalances
            WHERE rn = 1
            ORDER BY Date ASC
        """
        
        data = self.cursor.execute(query, (from_date_str,)).fetchall()
        df = pd.DataFrame(data, columns=['Date', 'Balance'])
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.dropna(subset=['Balance'])
        # Convert Balance to numeric, removing any non-numeric entries
        df['Balance'] = pd.to_numeric(df['Balance'], errors='coerce') 
        df = df.dropna(subset=['Balance'])
        return df

    def fix_cal_date_bug(self) -> None:
        """
        The function will find all the dates in the in the Date column, in File table,
        which have have the first 4 chars equal to '0025' and will change them to '2025'.
        the function will only change the first 4 chars of the specific date string.
        print the queried rows before and after the change and only then commit the changes.
        """
        query = """
            SELECT Date
            FROM File
            WHERE Date LIKE '0025%'
        """
        rows = self.cursor.execute(query).fetchall()
        utils.log(f"Rows before fix: {rows}", 'system')
        if not rows:
            utils.log("No rows to fix.", 'system')
            return
        # Update the dates
        self.cursor.execute("""
            UPDATE File
            SET Date = '2025' || substr(Date, 5)
            WHERE Date LIKE '0025%'
        """)
        

    def search_transactions(self, params: dict) -> pd.DataFrame:
        """
        Search transactions with multiple filters
        params can include:
        - date_range: tuple(start_date, end_date)
        - name: str
        - value_range: tuple(min_val, max_val)
        - table: str ("BankTransactions" or "CardTransactions")
        - category: str
        """
        query_parts = []
        query_values = []
        
        # Base query
        query = """
            SELECT * FROM (
            SELECT 
                'BankTransactions' as TableName,
                ID,
                Date as 'Date_Executed_Date',
                Name,
                Category,
                Out as 'Out_Transaction_Value',
                Income as 'Income_Charge_Value',
                Extra_Info,
                Description
            FROM BankTransactions
            UNION ALL
            SELECT
                'CardTransactions' as TableName,
                ID,
                Executed_Date as 'Date_Executed_Date',
                Name,
                Category,
                Transaction_Value as 'Out_Transaction_Value',
                Charge_value as 'Income_Charge_Value',
                Extra_Info,
                Description
            FROM CardTransactions) AS combined
        """

        # Add WHERE clause if we have any filters
        if params:
            query += " WHERE "
            
            if 'date_range' in params:
                start, end = params['date_range']
                if start:
                    query_parts.append("Date_Executed_Date >= ?")
                    query_values.append(start)
                if end:
                    query_parts.append("Date_Executed_Date <= ?")
                    query_values.append(end)

            if 'name' in params:
                query_parts.append("(Name LIKE ? OR Extra_Info LIKE ? OR Description LIKE ?)")
                query_values.extend([f"%{params['name']}%", f"%{params['name']}%", f"%{params['name']}%"])

            if 'value_range' in params:
                min_val, max_val = params['value_range']
                if min_val is not None and max_val is not None:
                    query_parts.append("((Out_Transaction_Value >= ? AND Out_Transaction_Value <= ?) OR (Income_Charge_Value >= ? AND Income_Charge_Value <= ?))")
                    query_values.extend([min_val, max_val, min_val, max_val])

            if 'table' in params:
                query_parts.append("TableName = ?")
                query_values.append(params['table'])

            if 'category' in params:
                query_parts.append("Category = ?")
                query_values.append(params['category'])

            query += " AND ".join(query_parts)

        # Execute query
        results = self.cursor.execute(query, query_values).fetchall()
        
        # Convert to DataFrame
        df = pd.DataFrame(results, columns=[d[0] for d in self.cursor.description])
        return df

    def get_Cash_Transactions(self, datetime: datetime | None = None) -> pd.DataFrame:
        """
        The function will return all the transactions in the CashTransactions table.
        given a date that is not None, the function will return only transactions
        that were executed in the same month of the given date.
        """
        if datetime is None:
            data = self.cursor.execute("""
                                SELECT * FROM CashTransactions
                                """).fetchall()
        else:
            month_str = str(datetime.month).zfill(2)
            year_str = str(datetime.year)
            data = self.cursor.execute("""
                                SELECT * FROM CashTransactions
                                WHERE strftime('%m', Execution_Date) = ?
                                AND strftime('%Y', Execution_Date) = ?
                                """, (month_str, year_str,)).fetchall()
        
        return pd.DataFrame(data=data, columns=[d[0] for d in self.cursor.description])


    def change_description_by_id(self) -> None:
        """Edit transaction description by ID and table"""
        param1 = utils.template_menu(['Bank', 'Card'], msg='Choose the relevant table:')
        param2 = input('Insert transaction ID: ')
        param3 = input('Insert new description: ')

        if param1 == 0:
            table = "BankTransactions"
        else:
            table = "CardTransactions"

        query = f"""SELECT * FROM {table} WHERE id = ?"""
        prev = self.cursor.execute(query, (param2,)).fetchall()
            
        query = f"""UPDATE {table} SET Description = ? WHERE id = ?"""            
        self.cursor.execute(query, (param3, param2,))
            
        query = f"""SELECT * FROM {table} WHERE id = ?"""
        after = self.cursor.execute(query, (param2,)).fetchall()

        utils.log(f"Before: {prev}")
        utils.log(f"After: {after}")


    def is_cash_transaction_exists(self, transaction_id: int) -> bool:
        """
        Check if a cash transaction with the given ID exists.
        
        Args:
            transaction_id (int): ID of the cash transaction to check.
        Returns:
            bool: True if the transaction exists, False otherwise.
        """
        query = "SELECT 1 FROM CashTransactions WHERE ID = ?"
        result = self.cursor.execute(query, (transaction_id,)).fetchone()
        return result is not None
    
    def delete_cash_transaction(self, transaction_id: int) -> bool:
        """
        Delete a cash transaction by ID.
        use is_cash_transaction_exists to make sure transaction exists before using
        
        Args:
            transaction_id (int): ID of the cash transaction to delete.
        Returns:
            bool: True if deletion was successful, False otherwise.
        """
        try:
            self.cursor.execute("DELETE FROM CashTransactions WHERE ID = ?", (transaction_id,))
            self.connection.commit()
            utils.log(f"Cash transaction with ID {transaction_id} deleted successfully.", "system")
            return True
        except Exception as e:
            utils.log(f"Error deleting cash transaction: {str(e)}", "error")
            return False
        

    def query_monthly_transactions(self, date: datetime, tables: list[str]) -> pd.DataFrame:
        """
        The function receives a date and a list of table names (BankTransactions and/or CardTransactions).
        The function will return all the transactions from the given month in a single dataframe.
        """
        month_str = str(date.month).zfill(2)
        year_str = str(date.year)
        all_data = []

        # the following month and year
        next_month_str = str((date.month % 12) + 1).zfill(2)
        next_year_str = str(date.year + (1 if date.month == 12 else 0))
        

        if "BankTransactions" in tables:
            bank_data = self.cursor.execute("""
                                SELECT *, 'BankTransactions' AS TableName
                                FROM BankTransactions
                                WHERE 
                                    (strftime('%m', Date) = ? AND strftime('%Y', Date) = ?)
                                """, (month_str, year_str, )).fetchall()
            bank_df = pd.DataFrame(data=bank_data, columns=[d[0] for d in self.cursor.description])
            all_data.append(bank_df)

        if "CardTransactions" in tables:
            card_data = self.cursor.execute("""
                                SELECT *, 'CardTransactions' AS TableName
                                FROM CardTransactions
                                WHERE 
                                    (strftime('%m', Executed_Date) = ? AND strftime('%Y', Executed_Date) = ?)
                                    or
                                    (strftime('%m', Charge_Date) = ? AND strftime('%Y', Charge_Date) = ?)
                                """, (month_str, year_str, next_month_str, next_year_str,)).fetchall()
            card_df = pd.DataFrame(data=card_data, columns=[d[0] for d in self.cursor.description])
            all_data.append(card_df)

        if all_data:
            combined_df = pd.concat(all_data, ignore_index=True)
            return self.apply_splits_to_df(combined_df)
        else:
            return pd.DataFrame()  # Return empty DataFrame if no valid tables provided
        
    def fix_column_date_format(self, table_name: str, column_name: str) -> pd.DataFrame:
        """
        The function will fix the date format in the specified column of the specified table using the date_ready function.
        a df will be returned, indicating if the entery was fixed, failed to be fixed or was already correct.
        """
        query = f"""
            SELECT ID, {column_name}
            FROM {table_name}
        """
        rows = self.cursor.execute(query).fetchall()
        results = []

        for row in rows:
            entry_id, date_str = row
            try:
                fixed_date = utils.date_ready(date_str)
                # Update the database with the fixed date
                update_query = f"""
                    UPDATE {table_name}
                    SET {column_name} = ?
                    WHERE ID = ?
                """
                self.cursor.execute(update_query, (fixed_date, entry_id))
                results.append((entry_id, fixed_date, 'Fixed'))
            
            except Exception:
                results.append((entry_id, date_str, 'Failed to fix'))
            
        self.connection.commit()
        return pd.DataFrame(results, columns=['ID', column_name, 'Status'])

    # ── Transaction Split methods ──────────────────────────────────────────────

    def get_splits_for_transaction(self, original_table: str, original_id: int) -> list:
        """Return all split rows for a given original transaction."""
        rows = self.cursor.execute("""
            SELECT ID, Amount, Description, Category, Created_At
            FROM TransactionSplits
            WHERE Original_Table = ? AND Original_ID = ?
            ORDER BY ID
        """, (original_table, int(original_id))).fetchall()
        return [{'id': r[0], 'amount': r[1], 'description': r[2] or '',
                 'category': r[3], 'created_at': r[4]} for r in rows]

    def get_all_splits(self) -> list:
        """Return all split records as a list of dicts."""
        rows = self.cursor.execute("""
            SELECT ID, Original_Table, Original_ID, Amount, Description, Category
            FROM TransactionSplits
        """).fetchall()
        return [{'split_id': r[0], 'orig_table': r[1], 'orig_id': r[2],
                 'amount': r[3], 'description': r[4] or '', 'category': r[5]}
                for r in rows]

    def create_splits(self, original_table: str, original_id: int, splits: list) -> list:
        """
        Insert split rows. splits = [{'amount': float, 'description': str, 'category': str}, ...]
        Returns list of created TransactionSplits IDs.
        """
        ids = []
        for s in splits:
            self.cursor.execute("""
                INSERT INTO TransactionSplits (Original_Table, Original_ID, Amount, Description, Category)
                VALUES (?, ?, ?, ?, ?)
            """, (original_table, int(original_id),
                  float(s['amount']), s.get('description', '') or '', s['category']))
            ids.append(self.cursor.lastrowid)
        return ids

    def revert_splits(self, original_table: str, original_id: int) -> int:
        """Remove all splits for a transaction. Returns number of rows deleted."""
        self.cursor.execute("""
            DELETE FROM TransactionSplits
            WHERE Original_Table = ? AND Original_ID = ?
        """, (original_table, int(original_id)))
        return self.cursor.rowcount

    def apply_splits_to_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Replace split-original rows with their individual split rows.
        Expects raw column names (Out, Income, Transaction_Value) as returned by
        query_monthly_transactions() / SELECT *.
        Adds '_split_orig_id' column (NaN for non-split rows) so downstream
        code can set data-is-split / data-orig-id HTML attributes.
        """
        if df.empty:
            return df

        all_splits = self.get_all_splits()
        if not all_splits:
            return df

        if 'TableName' not in df.columns or 'ID' not in df.columns:
            return df

        split_keys = set((s['orig_table'], s['orig_id']) for s in all_splits)

        # Vectorised mask: which rows are split originals?
        mask_orig = pd.Series(False, index=df.index)
        for tbl, oid in split_keys:
            mask_orig |= (df['TableName'] == tbl) & (df['ID'] == oid)

        if not mask_orig.any():
            return df

        df_clean = df[~mask_orig].copy()
        new_rows = []

        for _, orig_row in df[mask_orig].iterrows():
            tbl    = str(orig_row['TableName'])
            oid    = int(orig_row['ID'])
            my_splits = [s for s in all_splits
                         if s['orig_table'] == tbl and s['orig_id'] == oid]

            is_spending = (
                (tbl == 'BankTransactions'  and float(orig_row.get('Out', 0) or 0) > 0) or
                (tbl == 'CardTransactions'  and float(orig_row.get('Transaction_Value', 0) or 0) > 0)
            )

            for s in my_splits:
                sr = orig_row.copy()
                sr['ID']              = s['split_id']   # use split ID as row identifier
                sr['_split_orig_id']  = oid              # remember original for revert
                sr['Category']        = s['category']
                if s['description']:
                    sr['Description'] = s['description']

                if tbl == 'BankTransactions':
                    if is_spending:
                        sr['Out']    = s['amount']
                        sr['Income'] = 0
                    else:
                        sr['Income'] = s['amount']
                        sr['Out']    = 0
                elif tbl == 'CardTransactions':
                    sr['Transaction_Value'] = s['amount'] if is_spending else -s['amount']
                    sr['Charge_Value']      = s['amount']

                new_rows.append(sr)

        if new_rows:
            df_splits = pd.DataFrame(new_rows)
            return pd.concat([df_clean, df_splits], ignore_index=True)
        return df_clean

    # ── Bills tracker ──────────────────────────────────────────────────────────

    def get_bill_types(self) -> list:
        rows = self.cursor.execute(
            "SELECT ID, Name, Color, GroupName FROM BillTypes ORDER BY GroupName NULLS LAST, ID"
        ).fetchall()
        return [{'id': r[0], 'name': r[1], 'color': r[2] or '#1e9d8b', 'group': r[3] or ''} for r in rows]

    def add_bill_type(self, name: str, color: str = '#1e9d8b', group: str = '') -> int:
        self.cursor.execute(
            "INSERT INTO BillTypes (Name, Color, GroupName) VALUES (?, ?, ?)",
            (name.strip(), color, group.strip() or None)
        )
        return self.cursor.lastrowid

    def update_bill_type(self, type_id: int, name: str, color: str, group: str = ''):
        self.cursor.execute(
            "UPDATE BillTypes SET Name=?, Color=?, GroupName=? WHERE ID=?",
            (name.strip(), color, group.strip() or None, type_id)
        )

    def delete_bill_type(self, type_id: int):
        self.cursor.execute("DELETE FROM BillEntries WHERE BillType_ID = ?", (type_id,))
        self.cursor.execute("DELETE FROM BillTypes WHERE ID = ?", (type_id,))

    def get_bill_entries(self) -> list:
        rows = self.cursor.execute("""
            SELECT e.ID, e.BillType_ID, e.Start_Month, e.End_Month,
                   e.Transaction_Table, e.Transaction_ID, e.Amount, e.Note, e.Is_Filler,
                   COALESCE(b.Name,          c.Name)           AS TxName,
                   COALESCE(b.Date,          c.Executed_Date)  AS TxDate,
                   COALESCE(b.Category,      c.Category)       AS TxCategory,
                   COALESCE(b.Description,   c.Description)    AS TxDescription,
                   COALESCE(b.Extra_Info,    c.Extra_Info)     AS TxExtraInfo,
                   b.Ref                                       AS TxRef,
                   b.Balance                                   AS TxBalance,
                   b.Value_Date                                AS TxValueDate,
                   c.CardID                                    AS TxCardID,
                   c.Charge_Date                               AS TxChargeDate,
                   c.Charge_Value                              AS TxChargeValue,
                   c.Charge_Currency                           AS TxChargeCurrency,
                   COALESCE(
                     CASE WHEN b.Income > 0 THEN CAST(b.Income AS REAL)
                          ELSE CAST(b.Out AS REAL) END,
                     ABS(CAST(c.Transaction_Value AS REAL))
                   )                                           AS TxAmount
            FROM BillEntries e
            LEFT JOIN BankTransactions b
              ON e.Transaction_Table='BankTransactions' AND e.Transaction_ID=b.ID
            LEFT JOIN CardTransactions c
              ON e.Transaction_Table='CardTransactions' AND e.Transaction_ID=c.ID
            ORDER BY e.Start_Month
        """).fetchall()
        return [{'id': r[0], 'bill_type_id': r[1], 'start_month': r[2],
                 'end_month': r[3], 'transaction_table': r[4], 'transaction_id': r[5],
                 'amount': r[6], 'note': r[7] or '', 'is_filler': bool(r[8]),
                 'tx_name':          r[9]  or '',
                 'tx_date':         (r[10] or '')[:10],
                 'tx_category':      r[11] or '',
                 'tx_description':   r[12] or '',
                 'tx_extra_info':    r[13] or '',
                 'tx_ref':           r[14] or '',
                 'tx_balance':       r[15],
                 'tx_value_date':   (r[16] or '')[:10],
                 'tx_card_id':       r[17] or '',
                 'tx_charge_date':  (r[18] or '')[:10],
                 'tx_charge_value':  r[19],
                 'tx_charge_currency': r[20] or '',
                 'tx_amount':         r[21]}
                for r in rows]

    def check_bill_entry_overlap(self, bill_type_id: int, start_month: str,
                                 end_month: str, exclude_id: int = None) -> str | None:
        """Return an error string if the date range overlaps an existing entry of the same type, else None."""
        # Normalize: 'YYYY-MM' → 'YYYY-MM-01' for start, 'YYYY-MM-31' for end
        def ns(m): return m if len(m) > 7 else m + '-01'
        def ne(m): return m if len(m) > 7 else m + '-31'
        params = [bill_type_id, ne(end_month), ns(start_month)]
        sql = """
            SELECT e.ID, e.Start_Month, e.End_Month, bt.Name
            FROM BillEntries e
            JOIN BillTypes bt ON bt.ID = e.BillType_ID
            WHERE e.BillType_ID = ?
              AND CASE WHEN LENGTH(e.Start_Month)=7 THEN e.Start_Month||'-01' ELSE e.Start_Month END < ?
              AND CASE WHEN LENGTH(e.End_Month)=7   THEN e.End_Month  ||'-31' ELSE e.End_Month   END > ?
        """
        if exclude_id is not None:
            sql += " AND e.ID != ?"
            params.append(exclude_id)
        row = self.cursor.execute(sql, params).fetchone()
        if row:
            return f"חפיפה עם רשומה קיימת ({row[1]} – {row[2]})"
        return None

    def add_bill_entry(self, bill_type_id: int, start_month: str, end_month: str,
                       transaction_table=None, transaction_id=None,
                       amount=None, note=None, is_filler=False) -> int:
        self.cursor.execute("""
            INSERT INTO BillEntries
            (BillType_ID, Start_Month, End_Month, Transaction_Table, Transaction_ID,
             Amount, Note, Is_Filler)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (bill_type_id, start_month, end_month, transaction_table,
              transaction_id, amount, note, 1 if is_filler else 0))
        return self.cursor.lastrowid

    def update_bill_entry(self, entry_id: int, start_month: str, end_month: str, note=None,
                          transaction_table=None, transaction_id=None, amount=None, is_filler=None):
        sets   = ["Start_Month=?", "End_Month=?", "Note=?"]
        params = [start_month, end_month, note]
        if transaction_table is not None:
            sets.append("Transaction_Table=?"); params.append(transaction_table)
        if transaction_id is not None:
            sets.append("Transaction_ID=?"); params.append(transaction_id)
        if amount is not None:
            sets.append("Amount=?"); params.append(amount)
        if is_filler is not None:
            sets.append("Is_Filler=?"); params.append(1 if is_filler else 0)
        params.append(entry_id)
        self.cursor.execute(f"UPDATE BillEntries SET {', '.join(sets)} WHERE ID=?", params)

    def delete_bill_entry(self, entry_id: int):
        self.cursor.execute("DELETE FROM BillEntries WHERE ID = ?", (entry_id,))

    def dismiss_bill_suggestion(self, transaction_name: str):
        self.cursor.execute("""
            INSERT OR IGNORE INTO BillSuggestionsDismissed (Transaction_Name) VALUES (?)
        """, (transaction_name,))

    def get_bill_suggestions_dismissed(self) -> set:
        rows = self.cursor.execute(
            "SELECT Transaction_Name FROM BillSuggestionsDismissed"
        ).fetchall()
        return {r[0] for r in rows}
