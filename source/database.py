import sqlite3
from datetime import datetime


class DataBase:

    def __init__(self):

        self.connection = sqlite3.connect('databse.db')
        self.cursor = self.connection.cursor()

        self.cursor.execute("""CREATE TABLE IF NOT EXISTS Card (
                                cardID          CHAR(4)     PRIMARY KEY,
                                description     TEXT
                                );"""
                            )

        self.cursor.execute("""CREATE TABLE IF NOT EXISTS Transactions (
                                ID          INTEGER    PRIMARY KEY,
                                date        DATE NOT   NULL,
                                amount      INT NOT    NULL,
                                source      CHAR,
                                description TEXT,
                                cardID      CHAR(4),
                                FOREIGN KEY(cardID)
                                REFERENCES Card(cardID)
                                );"""
                            )

    def insert_transaction(self,
                           date: datetime,
                           amount: int,
                           source: str,
                           description: str = "",
                           card_id: str = None):
        '''
        Insert a new transaction to local DB.
        '''
        self.cursor.execute(f"""
            INSERT INTO Transactions(date, amount, source, description, cardID) VALUES(?, ?, ?, ?, ?)
            """, (date, amount, source, description, card_id))
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
