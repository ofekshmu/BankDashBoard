from database import DataBase
from parser import Parser
from config import log
from decorators import Status


class appManager:

    def __init__(self):
        self.db = DataBase()
        self.parser = Parser()

    def run(self):

        # table = self.parser.parse_credit(self.parser.get_files()[1])
        # for row in table:
        #     self.db.insert_transaction(row[0], row[1], row[2], row[3], row[7], row[9], self.parser.get_files()[1])

        files = self.parser.get_files()
        for f in files:
            if not self.parser.read(f):
                continue
            if not self.parser.validate():
                continue

            date, c1, c2 = self.parser.get_metadata()

            res = self.__check_file_status(date, c1, c2, f)

            match res:
                case Status.new:
                    self.db.insert_file(f,
                                        date,
                                        description="Auto add",
                                        trans_count=c1 + c2)
                    table = self.parser.get_transactions()
                    self.insert_transactions(table, f)
                case Status.exists:
                    pass
                case Status.update:
                    pass
                case other:
                    pass
            log(f'~ Loop END ~ Ended with status {res}', category='system')

        self.db.close()

    def __check_file_status(self, date, c1, c2, file_name: str):
        log(f'c1: {c1} , c2: {c2}', category='debug')
        date_b = False
        name_b = False
        
        if DataBase().file_name_exists(file_name):
            name_b = True
            log(f'SYSTEM: {file_name} - Name already exists.', category='system')

        if DataBase().date_exists(date):
            date_b = True
            log(f'SYSTEM: {date} already exists.', category='system')

        if date_b and name_b:
            count_existing = DataBase().transaction_count(file_name)
            log(f'count_existing: {count_existing}', category='debug')
            if count_existing == c1 + c2:
                log(f'SYSTEM: Skipping File...', category='system')
                return Status.exists
            elif count_existing < c1 + c2:
                log(f'SYSTEM: Updating file...', category='system')
                log(f"\n{'-'*30}\nSYSTEM: TODO THIS...\n{'-'*30}\n", category='system')
                return Status.update
        else:
            log(f'SYSTEM: date is {date_b} | name is {name_b}', category='system')
            log(f'SYSTEM: adding {file_name} to db.', category='system')
            return Status.new 

    def insert_transactions(self, table, file_name):
        for row in table:
            self.db.insert_transaction(row[0], row[1], row[2], row[3], row[7], row[9], file_name)







