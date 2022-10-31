from Constants import log, name_he
from File import File


class Context:

    file: File

    def setFile(self, file: File = None) -> None:
        if file is not None:
            self.file = file
        else:
            log(f"file is of class {type(file)}.", 'error')

    def render(self) -> bool:
        log(f'Reading{name_he(self.file.name)}... {self.file}', 'system')
        if not self.file.load():
            log(f'Failed reading file: {self.file.name}', category='error')
            return False
        if not self.file.validate_bank_number():
            log(f'Bank Account number in file: {name_he(self.file.name)} , does not match!', category='error')
            return False
        print('-> [SYSTEM]: Validation...\t', end='')
        if not self.file.validate_headers():
            print('FAILED.')
            return False
        else:
            print('Completed.')
        print('-> [SYSTEM]: Parsing...\t\t', end='')
        if not self.file.parse():
            print('FAILED.')
            return False
        else:
            print('Completed.')
        print('-> [SYSTEM]: Inserting...\t')
        if not self.file.insert():
            print('FAILED.')
            return False
        else:
            log('Completed.', 'system')

        return True
