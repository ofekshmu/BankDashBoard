from Parser import Parser


class AppManager:

    def __init__(self):
        self.db = DataBase()
        self.parser = Parser()

    def run(self):

        while next(self.parser):
            file = self.parser.create_file()
            if file.validate():
                raise ValueError()
            if file.clean():
                raise ValueError()
            if file.reduce():
                raise ValueError()
            if file.insert:
                raise ValueError()

    