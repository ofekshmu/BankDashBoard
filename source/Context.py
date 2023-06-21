from src_utils.utils import utils
from File import File
from database import DataBase


class Context:

    file: File
    counter: int

    def setFile(self, file: File = None) -> None:
        if file is not None:
            self.file = file
        else:
            utils.log(f"In class Context -> function setFile:\nFile was not inserted.", 'error')

    def render(self) -> bool:
        """
        The render function intiates the flow of handaling the input files.
        The flow includes reading, validating, parsing, cleaning and insertion.
        """
        utils.log(f"{100*'-'} file no' {self.counter}")
        utils.log(f'Reading {utils.name_he(self.file.name)}... {self.file}', 'system')
        if not self.file.load():
            utils.log(f'Failed reading file: {self.file.name}', category='error')
            return False

        # if not self.file.validate_bank_number():
        #     utils.log(f'Bank Account number in file: {utils.name_he(self.file.name)} , does not match!', category='error')
        #     return False

        # if not self.file.validate_headers():
        #     utils.log("Validation...\tFAILED.", "warning")
        #     return False
        # else:
        #     utils.log("Validation...\tCompleted.", "system")

        if not self.file.parse():
            utils.log('Parsing... \tFAILED', "error")
            return False
        else:
            utils.log('Parsing... \tCOMPLETED', "system")

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
            utils.log('Completed.', 'system')

        DataBase().commit_changes()
        utils.log('Changes Commited to data base.', 'system')

        return True
