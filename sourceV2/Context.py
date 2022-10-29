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
        log(f'Reading {name_he(self.file.name)}...', 'system')
        if not self.file.load():
            log(f'Failed reading file: {self.file.name}', category='error')
            return False
        if not self.file.validate_bank_number():
            log(f'Bank Account number in file: {name_he(self.file.name)} , does not match!', category='error')
            return False
        if not self.file.validate_headers():
            log(f'Headers in file: {self.file.name} , does not match!', 'error')
        log(f'Validation in file: {name_he(self.file.name)} Completed.', 'system')

        return True
