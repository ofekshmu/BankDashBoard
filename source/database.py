import sqlite3
from datetime import datetime

# local imports
from decorators import try_catch


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
            Transaction_count   INT         NOT NULL,
            Last_update         DATE        NOT NULL
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

    @try_catch
    def insert_transaction(self,
                           cardID: str,
                           transaction_date: datetime,
                           business_name: str,
                           amount: int,
                           transaction_type: str,
                           charge_date: datetime,
                           source_file: str,
                           description: str = ""):
        '''
        Insert a new transaction to local DB.
        '''
        if not self.is_card_exists(cardID):
            print(f'New card found: ->{cardID}<-')
            if not self.insert_card(cardID, "Auto Insertion"):
                return False
            print(f'Card ID {cardID} has been added!')

        self.cursor.execute(f"""
            INSERT INTO Transactions(cardID, transaction_date, business_name,
                amount, transaction_type, charge_date, source_file, description)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """, (cardID, transaction_date, business_name, amount,
                  transaction_type, charge_date, source_file, description)
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
    
    @try_catch
    def update_files(self,
                     name: str,
                     date: datetime,
                     transaction_count: int,
                     description: str = '-'):
        last_update = datetime.now()
        self.cursor.execute(f"""
            INSERT INTO Files(Name, Date, Description,
                Transaction_count, Last_update)
            VALUES(?, ?, ?, ?, ?)
            """, (name, date, description, transaction_count, last_update)
            )

    @try_catch
    def file_name_exists(self, file_name):
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
    def date_exists(self, date: datetime):
        '''
        Returns True if a file with the given date exists.
        False otherwise.
        '''
        ans = self.cursor.execute("""
                    SELECT 1
                    FROM File
                    WHERE Date = ?;
                """, (date,)).fetchone()
        return False if ans is None else True

    @try_catch
    def transaction_count(self, file_name):
        '''
        Returns True if a file with the given date exists.
        False otherwise.
        '''
        res = self.cursor.execute("""
                    SELECT Transaction_count
                    FROM File
                    WHERE Name = ?;
                """, (file_name,)).fetchone()
        return res

    @try_catch
    def close(self):
        '''
        Close The connection to the database.
        '''
        self.connection.close()
