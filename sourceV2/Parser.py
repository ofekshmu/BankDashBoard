from os import listdir
from os.path import isfile, join


class Parser():
    def __init___(self):
        self.n = 0
        self.file_names = []
        for file in listdir(local.XLSX_PATH):
            if isfile(join(local.XLSX_PATH, file)) and file.endswith(local.EXTENSION):
                self.file_names.append(file)
        
        log(f'found {len(self.files)} files in {local.XLSX_PATH} ending with {local.EXTENSION}.', category='system')


    def __next__(self):
        if self.n < len(self.file_names):
            result = self.file_names[self.n]
            self.n += 1
            return result
        else:
            return None

    def create_file(self):
        file_name = self.file_names[self.n]

        res = self.match_file(file_name)
        sheet = self.read(file_name)

        return self.parse()

    def match_file(file_name):
        """
        Check the file_name received and categorize into one of the following
        1->
        2->
        3->
        """
        pass

    def read(file_name):
        """
        The file is read and a work sheet is returned.
        """
        pass

    def parse(file_name):
        """
        The function reads relevant file data into the File class
        """
