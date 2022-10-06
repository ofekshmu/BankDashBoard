from database import DataBase
from datetime import datetime


def main():
    mydb = DataBase()
    mydb.insert_card('1234', 'testSDAF')
    mydb.insert_transaction('435',
                            datetime.now(),
                            230,
                            "test des",
                            '1234')
    mydb.close()


if __name__ == "__main__":
    main()
