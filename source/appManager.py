from database import DataBase
from parser import Parser
from config import creditFile, log, VisaFile
from decorators import Status


class appManager:

    def __init__(self):
        self.db = DataBase()
        self.parser = Parser()

    def run(self):
        files = self.parser.get_files()
        for f in files:
            if not self.parser.read(f):
                continue
            file_type = self.parser.identify_and_validate()
            if file_type is None:
                log(f'FILE DROPPED. {f} was not identified.', category='error')
                break

            date, c1, c2 = self.parser.get_metadata()
            res = self.check_file_status(date, c1, c2, f)

            match res:
                case Status.new:
                    self.db.insert_file(f, date,
                                        description="Auto add",
                                        trans_count=c1 + c2)
                    table = self.parser.get_transactions(c1, c2)
                    self.insert_data(file_type, table, f)
                case Status.exists:
                    log(f"File Exists.. Skipping..", 'system')
                case Status.update:
                    log(f"case update NOT IMPLEMENTED", 'error')
                case other:
                    log(f"Received unknown status: {res}", 'error')

        self.db.close()

    def check_file_status(self, date, c1, c2, file_name: str):
        log(f'c1= {c1}, c2= {c2}, date= {date}', category='debug')
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

    def insert_data(self, type, table, file_name):
        """
        ?
        """
        if type == VisaFile:
            for row in table:
                if row[4] == 0:
                    amount = row[5]
                elif row[5] == 0:
                    amount = -row[4]
                else:
                    log('None of the amount values are ZERO!', 'error')
                self.db.insert_bank_transaction(ref=row[3],
                                                date=row[0],
                                                date_value=row[1],
                                                source_dest=row[2],
                                                amount=amount,
                                                balance=row[6],
                                                desc=row[7],
                                                source_file=file_name)
        elif type == creditFile:
            for row in table:
                self.db.insert_transaction(row[0], row[1], row[2], row[3], row[7], row[9], file_name)
        else:
            print("Case ({self.type}) not implemented in function 'insert_data'", 'error')


