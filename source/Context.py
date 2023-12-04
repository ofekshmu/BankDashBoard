from src_utils.utils import utils
from File import File
from database import DataBase
from Constants import Local

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
        
        utils.log("Validating...", "system")
        if not self.file.validate_headers():
            return False
        utils.log("Validation...\tCompleted.", "system")

        utils.log('Parsing...', "system")
        if not self.file.parse():
            return False
        utils.log("Parsing...\tCompleted.", "system")

        utils.log('Cleaning...', "system")
        if not self.file.clean():
            return False
        utils.log('Cleaning...\tCompleted', "system")

        utils.log('Inserting...', "system")
        if not self.file.insert():
            return False
        utils.log('Inserting...\tCompleted', "system")

        file_name, format_name = self.file.get_info()
        utils.move_file_to_directory(file_path=f"Inputs01/{file_name}",
                                    destination_directory=f"{Local.VERIFIED_FOLDER}//{format_name}")
    
        DataBase().commit_changes()
        utils.log('Changes Commited to data base.', 'system')


        return True
