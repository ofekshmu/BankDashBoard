import sqlite3
from datetime import datetime


class database:

    def __init__(self):
        # create tables if does not exist
        pass

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