from database import DataBase
from datetime import datetime
from parser import Parser


def main():
    p = Parser()
    # mydb = DataBase()
    # mydb.insert_card('1234', 'testSDAF')
    # mydb.insert_transaction('435',
    #                         datetime.now(),
    #                         230,
    #                         "test des",
    #                         '1234')
    # mydb.close()
    ans = p.parse_credit(p.get_files()[1])
    print(ans)


if __name__ == "__main__":
    main()
