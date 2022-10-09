import sqlite3
from datetime import datetime


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
            CREATE TABLE IF NOT EXISTS Transactions (
            ID                  INTEGER     PRIMARY KEY ,
            cardID              CHAR(4)                 ,
            transaction_date    DATE        NOT NULL    ,
            business_name       CHAR                    ,
            amount              INT         NOT NULL    ,
            transaction_type    CHAR                    ,
            charge_date         DATE        NOT NULL    ,
            description         TEXT                    ,
            FOREIGN KEY(cardID)
            REFERENCES Card(cardID)
            );"""
                            )

    def insert_transaction(self,
                           cardID: str,
                           transaction_date: datetime,
                           business_name: str,
                           amount: int,
                           transaction_type: str,
                           charge_date: datetime,
                           description: str = ""):
        '''
        Insert a new transaction to local DB.
        '''
        self.cursor.execute(f"""
            INSERT INTO Transactions(cardID, transaction_date, business_name,
                amount, transaction_type, charge_date, description)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """, (cardID, transaction_date, business_name, amount,
                  transaction_type, charge_date, description)
            )
        self.connection.commit()

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

    def close(self):
        '''
        Close The connection to the database.
        '''
        self.connection.close()
