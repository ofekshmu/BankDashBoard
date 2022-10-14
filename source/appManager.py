from database import DataBase
from parser import Parser


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
            if not self.parser.validate(f):
                print(f'file {f} is INVALID.')
                continue
            
            meta_data = self.parse.get_meta(f)

            res = self.__check_file_status(meta_data)

            match res:
                case 'a':
                    pass
                case other:
                    pass

        self.db.close()

    def __check_file_status():
        pass
