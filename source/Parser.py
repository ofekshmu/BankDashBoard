from os import listdir
from os.path import isfile, join
from Constants import InnerCredit, OuterCredit, BankTransactions, Sortion
from OuterCreditFile import OuterCreditFile
from InnerCreditFile import InnerCreditFile
from BankTransactionsFile import BankTransactionsFile
from datetime import datetime
from File import File
from Configurations.Formats import Formats

# Local
from Constants import Local
from src_utils.utils import utils


class Parser():

    __instance = None

    @staticmethod
    def getInstance():
        """ Static access method """
        if Parser.__instance is None:
            Parser()
        return Parser.__instance

    def __init__(self):
        """ Virtually private constructor. """
        if Parser.__instance is not None:
            raise Exception("This class is a singleton!")
        else:
            Parser.__instance = self

            self.idx = 0
            self.type_to_name = {}
            self.names = []

            utils.log(f"Looking for files...", 'system')

            # def to_date(name: str) -> datetime:
            #     """
            #     Helper function That extracts the date of format XX_XX_XXXX
            #     out of a file str name. Returns a datetime object.
            #     """
            #     import re
            #     try:
            #         date_str = re.search("\w{1,2}_\w{1,2}_\w{4}", name).group()
            #     except Exception as e:
            #         utils.log(f"The file named {utils.name_he(name)} is of unknown format.", "error")
            #     date = date_str.split("_")
            #     import datetime
            #     return datetime.datetime(int(date[2]), int(date[1]), int(date[0]))

            # def to_num(name: str):
            #     """
            #     Receives the name of an outer credit file and returns the contained number
            #     """
            #     import re
            #     num_str = re.search("_\d{1,}", name).group()
            #     return num_str[1:]

            def is_exists(name: str, file_type) -> bool:
                """
                The function receives the name of the file(name is specified with the file extension) and the
                file type. True will be returned if a file with the same name was allready parsed and false otherwise.
                """
                # strip the extension to get the name only.
                stipped_name = name[:name.find('.')]
                if file_type not in self.type_to_name.keys():
                    return False
                for k in self.type_to_name[file_type].keys():
                    if stipped_name in k:
                        return True
                return False
            
            def is_valid_extension(name: str) -> bool:
                """
                Returns True if the file contains a valid extension and False otherwise.
                Valid extension should be stated in the Format.py file, Under Formats -> EXTENTIONS.
                """
                for ext in Formats.EXTENTIONS:
                    if name.endswith(ext):
                        return True
                utils.log(f"The file ({name}) with invalid extension.", "Error")
                return False

            for name in listdir(Local.INPUT_FOLDER):
                if isfile(join(Local.INPUT_FOLDER, name)) and \
                        is_valid_extension(name):
                    file_type, consts = self.__identify(name)

                    if file_type is None:
                        continue

                    # Sanity check - Written with blood
                    if is_exists(name, file_type):
                        utils.log(f"""The file '{utils.name_he(name)}' exists with a different extensions.
            What do you want to do?
            1 -> Skip the current copy, I will delete it later.
            2 -> Stop, I want to debug this.""", 'warning')
                        choise = int(input())
                        if choise == 1:
                            utils.log("Skipping.", category='system')
                            continue
                        elif choise == 2:
                            utils.log("Stopping program.", category='system')
                            exit()
                        else:
                            utils.log('Bad input!', 'error')

                    value = self.__extract_sortion_key(consts, name)

                    if file_type in self.type_to_name.keys():
                        self.type_to_name[file_type][name] = value
                    else:
                        self.type_to_name[file_type] = {name: value}

            # Sort the read file names according to dates/serial number
            for k, v in self.type_to_name.items():
                self.type_to_name[k] = {name: value for name, value in sorted(v.items(), key=lambda item: item[1])}

            # This Build is needed - DO NOT CHANGE
            # names list is built in the order of iteration to ensure
            # file names are read by the recency
            for dict in self.type_to_name.values():
                self.names += list(dict.keys())

            utils.log(f"found {len(self.names)} files in {Local.INPUT_FOLDER}", 'system')

    def __next__(self):
        """
        Call the to check if a file name is avaliable to read.
        """
        if self.idx < len(self.names):
            return True
        return False

    def get_next(self):
        """
        Get the next file name.
        Returns the file name and type.
        Call only after a successful 'next'.
        """
        name = self.names[self.idx]
        self.idx += 1
        return name, self.__identify(name)

    def __identify(self, file_name: str):
        """
        Identify the file Type.
        Received a file name and returns it's type.
        Grouping is made according to key words found in it's name.
        """
        res = None
        consts = None
        file_type = None
        if utils.id_method(InnerCredit, file_name):
            file_type, consts = InnerCreditFile, InnerCredit
        elif utils.id_method(OuterCredit, file_name):
            file_type, consts = OuterCreditFile, OuterCredit
        elif utils.id_method(BankTransactions, file_name):
            file_type, consts = BankTransactionsFile, BankTransactions
        else:
            utils.log(f"The file name: {file_name} was not identified, Ignoring...", 'warning')

        return file_type, consts

    def get_names(self, obj_class: File):
        """
        Return a list of names of file of type File.
        The names are Sorted by recency.
        """
        return [k for k in self.type_to_name[obj_class].keys()]

    def __extract_sortion_key(self, consts, name: str):
        """
        Receives a file name and type And Extracts the specified sorting element
        suited for the file type.
        In case of an outercredit file The serial number in the file name will be returned.
        Otherwise, the date in the file name will be retruned.
        """
        import re
        match consts.SORTION:
            case Sortion.BY_NAME_SERIAL:
                # Search for a serial number - a number larger than 4 digits
                # Since we want to ignore an year (4 digits), in case present
                srch_result = re.search("\d{5,}", name)
                if srch_result is None:
                    utils.log(f"There was a problem parsing the Serial from File {name}.", "error")
                return srch_result.group()[1:]
            case Sortion.BY_NAME_DATE:
                try:
                    date_str = re.search("\d{1,2}_\d{1,2}_\d{4}|\d{1}_\d{4}", name).group()
                except Exception as e:
                    utils.log(f"The file named {utils.name_he(name)} is of unknown format.", "error")
                date = date_str.split("_")
                import datetime
                if len(date) == 2:
                    date = (1, date[0], date[1])
                return datetime.datetime(int(date[2]), int(date[1]), int(date[0]))            