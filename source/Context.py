from Constants import log, name_he
from File import File


class Context:

    file: File
    counter: int

    def setFile(self, file: File = None) -> None:
        if file is not None:
            self.file = file
        else:
            log(f"In class Context -> function setFile:\nFile was not inserted.", 'error')

    def render(self) -> bool:
        """
        The render function intiates the flow of handaling the input files.
        The flow includes reading, validating, parsing, cleaning and insertion.
        """
        log(f"{100*'-'} file no' {self.counter}")
        log(f'Reading {name_he(self.file.name)}... {self.file}', 'system')
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
        print('-> [SYSTEM]: Cleaning...')
        if not self.file.clean():
            print('\t\t\t\tFAILED.')
            return False
        else:
            print('\t\t\t\tCompleted.')
        print('-> [SYSTEM]: Inserting...\t')
        if not self.file.insert():
            print('FAILED.')
            return False
        else:
            log('Completed.', 'system')

        return True
