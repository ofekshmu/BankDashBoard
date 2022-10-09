from database import DataBase
from datetime import datetime
from parser import Parser


def main():
    p = Parser()
    db = DataBase()
    # mydb.insert_card('1234', 'testSDAF')
    # mydb.insert_transaction('435',
    #                         datetime.now(),
    #                         230,
    #                         "test des",
    #                         '1234')
    # mydb.close()
    ans = p.parse_credit(p.get_files()[1])
    # print(ans)
    db.insert_card('6744', 'i inserted this')
    db.insert_card('5081', 'i inserted this')
    table = ans[0]
    for row in table:
        print(row)
        db.insert_transaction(row[1], row[3], row[2], row[7], row[0])
        print("inserted")


if __name__ == "__main__":
    main()
