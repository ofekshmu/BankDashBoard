from database import DataBase
from parser import Parser


class appManager:

    def __init__(self):
        self.db = DataBase()
        self.parser = Parser()

    def run(self):

        table = self.parser.parse_credit(self.parser.get_files()[1])
        for row in table:
            print(f'Inserting... : {row}')
            self.db.insert_transaction(row[0], row[1], row[2], row[3], row[7], row[9], self.parser.get_files()[1])
            print(f'Worked!')

        self.db.close()
