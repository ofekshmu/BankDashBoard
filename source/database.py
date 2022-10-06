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
                                ID          CHAR(4)     PRIMARY KEY,
                                date        DATE NOT    NULL,
                                amount      INT NOT     NULL,
                                description TEXT,
                                cardID      CHAR(4),
                                FOREIGN KEY(cardID)
                                REFERENCES Card(cardID)
                                );"""
                            )

        self.connection.commit()


    def insert_transaction(self,
                           id: str,
                           date: datetime,
                           amount: int,
                           description: str,
                           card_id: str = None):
        pass

    def insert_card(self,
                    id: str,
                    description: str):
        pass

    def close(self):
        '''
        Close The connection to the database.
        '''
        self.connection.close()
