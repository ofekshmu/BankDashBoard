from abc import abstractmethod
from src_utils.utils import utils
from Constants import Local, BANK_CARD_NUMBER
from typing import Union
from database import DataBase
from src_utils.ExcelReader import ExcelManager
from typing import Tuple
from Configurations.Formats import Formats

class File:
    def __init__(self, name: str, format_info: dict):
        '''
        File is read from local.XLSX_PATH.

        Parameters
        ----------
        name: a string indicating the name of the file
        bank_acc_loc: a 2 character string indicating the cell index
        initial row: a number indicating the header row
        headers: a list of string containing table headers
        '''
        self.name = name
        self.format_name = format_info["Format Name"]
        self.context = format_info["Context"]
        self.id_method = format_info["Identification method"]
        self.id_data = format_info["Identification data"]
        self.sortion_method = format_info["Sortion method"]
        self.sortion_key = format_info["Sortion key"]
        self.headers = format_info["Headers"]
        self.secondary_headers = format_info["Secondary Headers"]
        self.double_tables = format_info["Double tables"]
        self.header_row_idx = format_info["Header row index"]
        self.header_col_idx = format_info["Header col index"]
        self.adittional_data_field = format_info["Adittional data field"]
        self.independent = format_info["Independent"]
        self.flip = format_info["flip"]
        self.associated = format_info["associated"]

        # This value will determine the index of the secondary headers, if exists
        # The value is updated in the validate function
        self.secondary_headers_row_idx = -1

        self.table_1 = []
        self.table_2 = []
        self.flip_table_location = False

        # try:
        #     wb = xw.Book(join(Local.INPUT_FOLDER, self.name))
        #     self.sheet = wb.sheets[0]
        # except Exception as e:
        #     utils.log(f"Original error: {str(e)}\nFile read Failed!\nFile name: {self.name}\
        #         In File -> line 39\nMake sure the file is not open.", 'error')

    def load(self) -> bool:
        '''

        Parameters
        ----------
        file_name: a string indicating the name of the file
        '''
        try:
            ExcelManager().set_active_sheet(Local.INPUT_FOLDER + "\\" + self.name)
            return True
        except Exception as e:
            utils.log(str(e), category='debug')
            return False

    def validate_headers(self) -> bool:
        '''
        The function validates the table headers in the file.
        The values of the headers and the initial row are given in the Constants.py.
        '''
        valid = False   
        header_options = [self.headers, self.secondary_headers]
        for index, headers in enumerate(header_options):
            # Looks for the headers in a @err area of the given estimated
            err = 2
            temp = self.header_row_idx - err
            lower_bound = 1 if temp < 1 else temp
            for row in range(lower_bound, self.header_row_idx + err):
                for i in range(0, 3):   # error in col selection TODO: improve impl
                    valid = True
                    col = i
                    for name in headers:
                        utils.log(f'(FILE/Validate_headers) row number = {row}, col = {col}, name = {name[::-1]}', 'debug')
                        value = ExcelManager().read_cell(row, col)
                        if value != name:
                            valid = False
                            break
                        col += 1
                    if valid:
                        if row != self.header_row_idx:
                            utils.log(f"Headers were found at line {row}, Not in {self.header_row_idx} as specified\nIndex updated.", "warning")
                            self.header_row_idx = row
                        break
                if valid:
                    break
            if valid:
                if index == 1:
                    self.flip_table_location = True
                break

        if not valid:
            res = utils.template_menu(['Its Ok, the file is Empty. Mark it as Empty.', 'Skip File.', 'Break code.'],
                                      f'No Headers were found at the given initial index (err used = {err}), What do you want to do?')
            match res:
                case 0:
                    utils.log("Option not implemanted, skipping the file...", 'system')    # TODO
                    return False
                case 1:
                    return False
                case 2:
                    exit()

        else:
            utils.log("Initial headers match!", "system")

        if self.double_tables:
            row_idx = self.header_row_idx + 1
            col_idx = self.header_col_idx
            utils.log("col idx is not being checked for errors...File header valdiation", "warning")
            extracted_secondary_headers = ExcelManager().read_sheet(row_idx, 1, col_idx, len(self.secondary_headers))
            tries_left = 100
            while tries_left:
                if extracted_secondary_headers == self.secondary_headers:
                    utils.log("Secondary headers match!", "system")
                    self.secondary_headers_row_idx = row_idx
                    return True
                
                if "אין נתונים להצגה" == extracted_secondary_headers[0]:
                    utils.log("Secondary table is empty! Moving on..", "system")
                    self.secondary_headers_row_idx = row_idx
                    self.double_tables = False
                    return True

                row_idx += 1
                tries_left -= 1
                extracted_secondary_headers = ExcelManager().read_sheet(row_idx, 1, col_idx, len(self.secondary_headers))

            utils.log("Secondary Table was not found, Continuing...", "system")
            self.double_tables = False


        return True
    
        # def look_for_headers(header_lst: list, header_row_idx: int = -1, err: int = 2) -> Tuple[bool, int]:
            
        #     if header_row_idx < 0:
        #         tries_left = 100
        #         while tries_left:
        #             pass

        #     # determine lower bound for error radius
        #     temp = header_row_idx + 1 - err
        #     lower_bound = 1 if temp < 1 else temp

        #     for row in range(lower_bound, header_row_idx + err):
        #         for i in range(0, 3):   # error in col selection TODO: improve impl
        #             valid = True
        #             col = i
        #             for name in header_lst:
        #                 utils.log(f'(FILE/Validate_headers) row number = {row}, col = {col}, name = {name[::-1]}', 'debug')
        #                 if ExcelManager().read_cell(row, col) != name:
        #                     valid = False
        #                     break
        #                 col += 1
        #             if valid:
        #                 if row != header_row_idx:
        #                     utils.log(f"Headers were found at line {row}, Not in {self.header_row_idx} as specified\nIndex updated.", "warning")
        #                     header_row_idx = row
        #                 break
        #         if valid:
        #             break

        #     return valid, header_row_idx    

        # headers_are_valid, new_header_row_idx = look_for_headers(self.headers, self.header_row_idx)
        # if headers_are_valid:
        #     utils.log(f"Initial Headers are Valid.", "system")
        #     if new_header_row_idx != self.header_row_idx:
        #         self.header_row_idx = new_header_row_idx
        #         utils.log(f"Header row idx was updated to {new_header_row_idx}", "system")
        # else:
        #     utils.log(f"Initial table Headers were not found...", "system")
        
        # if not self.double_tables and headers_are_valid:
        #     return True

        # if self.double_tables:
        #     if headers_are_valid:
        #         secondary_headers_are_valid, new_sec_header_row_idx = look_for_headers(self.secondary_headers, self.secondary_headers_row_idx)
        #         if secondary_headers_are_valid:
        #             utils.log(f"Secondary Headers are Valid.", "system")
        #             if new_sec_header_row_idx != self.secondary_headers_row_idx:
        #                 self.secondary_headers_row_idx = new_sec_header_row_idx
        #                 utils.log(f"Secondary Header row idx was updated to {new_sec_header_row_idx}", "system")
        #         else:
        #             utils.log(f"Secondary Headers were not found...", "system")
        #         return True
        #     else:   # Initial headers are not valid, than check the second table as first.

        #         secondary_headers_are_valid, new_sec_header_row_idx = look_for_headers(self.secondary_headers, self.header_row_idx)
        #         if secondary_headers_are_valid:
        #             utils.log(f"Secondary Headers are Valid as initial table.", "system")
        #             if new_sec_header_row_idx != self.secondary_headers_row_idx:
        #                 self.secondary_headers_row_idx = new_sec_header_row_idx
        #                 utils.log(f"Secondary Header row idx was updated to {new_sec_header_row_idx}", "system")
        #             return True
        #         else:
        #             utils.log(f"Secondary Headers are Invalid as Initial Headers.", "system")
            
        # utils.log(f"Error Validating Headers... for file {self.name} ({self.format_name})", 'system')
        # return False


    @abstractmethod
    def parse(self) -> int:
        """
        Function responsibility is the complete parse of the data file.
        Currently, 'BankTransactionFile' and 'OuterCreditFile' are using this implementation.
        'Inner credit file is using a different one becuase of the complexity.
        """

        def read_table(header_lst: list, header_row_idx: int, first_col_idx: int) -> int:
            """
            bad_indexes indexes will varie from 0 to (counter - 1) to fit the use of python lists.
            """
            def is_bad_value(entire_row) -> bool:
                """
                Bad values are predetermined and are not included in the final parsed table.
                Bad values are used to ignore tables rows that do not represent transactions.
                These are identified using....
                """
                if entire_row[2] == "TOTAL FOR DATE" or\
                        entire_row[1] == 'סך חיוב בש"ח:' or\
                            entire_row[4] == 'יתרת פתיחה':
                    return True
                return False

            def Cash_advancment_fee(row):
                """
                'Cash Advance fee' row appears when using the ATM abroad. it has no dates and only shows the commission fee.
                In order to handle this case in the best way possible, uppon Discovery, an error will trigger, asking the user to merge the transactions
                by hand (change the input excel file and than try again)
                """
                if row[2] == "CASH ADVANCE FEE" and \
                    row[0] is None and \
                        row[1] is None:
                    return True
                return False
            
            bad_indexes = []
            row_counter = 0
            row_idx = header_row_idx + 1
            col_idx = first_col_idx

            table_entry = ExcelManager().read_sheet(row_idx, 1, col_idx, len(header_lst))
            cc_end = table_entry[0]

            if is_bad_value(table_entry):
                bad_indexes.append(row_idx - header_row_idx - 1)
                cc_end = "Bad value"

            while (cc_end is not None and \
                    cc_end != "עסקאות בחו˝ל"):
                row_counter += 1
                row_idx += 1
                table_entry = ExcelManager().read_sheet(row_idx, 1, col_idx, len(header_lst))
                cc_end = table_entry[0]

                if Cash_advancment_fee(table_entry):
                    utils.log("Cash Advancment row found, Please edit the excel file accordingly and try again. Check spec file for more info...", "error")

                if is_bad_value(table_entry):
                    bad_indexes.append(row_idx - header_row_idx - 1)    # Get the index relative to the header row
                    cc_end = "Bad value"

            bad_indexes = ', '.join([str(i) for i in bad_indexes])

            DataBase().insert_table_meta_data(self.name,
                                              self.format_name,
                                              self.card_number,
                                              header_row_idx + 1,
                                              col_idx,
                                              row_counter,
                                              bad_indexes)

            valid_rows = row_counter - len(bad_indexes.split(",")) if len(bad_indexes) >= 1 else row_counter
            utils.log(f'Meta data saved. Table data:\n\
            {"first data row index:":25s}{header_row_idx + 1}\n\
            {"initial col index:":25s}{first_col_idx}\n\
            {"number of rows:":25s}{row_counter}\n\
            {"Bad rows indexes:":25s}{bad_indexes}\n\
            {"valid rows:":25s}{valid_rows}', 'system')
            return valid_rows
        
        valid_rows = read_table(self.headers, self.header_row_idx, self.header_col_idx)

        if self.double_tables:
            valid_rows += read_table(self.secondary_headers, self.secondary_headers_row_idx, self.header_col_idx)

        return valid_rows


    def clean(self, flip: bool = False) -> bool:
        """
        Function will clean the read data.
        Given a table of transactions, it will change the table to contain only new
        ones which did not appear before.
        """

        def get_recent_file_info(sorted_dict: dict):
            keys = list(sorted_dict.keys())     # Convert keys to a list
            index = keys.index(self.name)       # Get the index of the target key
            
            if index > 0:                               # Check if there is a previous key
                prev_key = keys[index - 1]              # the file parsed before the current one (recent file)
                return prev_key, sorted_dict[prev_key]  # file name : file format
            else:
                raise ValueError("Not previous file...")
                return None                             # No previous key if the target is the first key
            
        def get_last_file_name(sorted_names: list) -> Union[str, None]:
            """
            The function receives a list containing all the file names of the same format at the current
            file being cleaned. It returns the name of the file which is hierarchically before the current one.
            Order is defined by the sortion key stated in the file's format table.
            In case there is not recent file before the current one, None is returned.
            """
            idx = sorted_names.index(self.name)
            if idx == 0:
                return None
            return sorted_names[idx - 1],

        def get_row(table):
            for i, row in enumerate(table):
                if len(row) < 9:
                    # this is an if stament sutied for a specific case of isra-card
                    return i, row
                if row[8] == "  * תנועות היום":
                    pass
                else:
                    return i, row

        def read_and_merge(meta_data: list[dict], root: str):
            if self.double_tables:
                [meta_0, meta_1] = meta_data

                table_0 = ExcelManager().set_active_sheet(root + "\\" + meta_0['File_Name'])\
                                        .read_sheet(meta_0['Initial_index'],
                                                    meta_0['Row_count'],
                                                    meta_0['Initial_col'],
                                                    len(self.headers))
                table_1 = ExcelManager().set_active_sheet(root + "\\" + meta_1['File_Name'])\
                                        .read_sheet(meta_1['Initial_index'],
                                                    meta_1['Row_count'],
                                                    meta_1['Initial_col'],
                                                    len(self.secondary_headers))

                # When a Table has only 1 row. The elements of the row are returned as a list,
                # And not as a list of rows as expected, That is why, another [] is added.
                if meta_0['Row_count'] == 1:
                    table_0 = [table_0]
                if meta_1['Row_count'] == 1:
                    table_1 = [table_1]

                # This row removes the bas indexes from the second table according to the meta data
                # indexes are in accordance to the first row of the table (not the excel numbering)
                # first table is not being checked for bad indexes.
                if meta_1["Bad_rows"] != '':
                    bad_indexes = [int(num) for num in meta_1["Bad_rows"].strip().split(',')]
                    table_1 = [table_1[i] for i in range(len(table_1)) if i not in bad_indexes]

                if meta_0["Bad_rows"] != '':
                    bad_indexes = [int(num) for num in meta_0["Bad_rows"].strip().split(',')]
                    table_0 = [table_0[i] for i in range(len(table_0)) if i not in bad_indexes]
                    
                return table_0, table_1
            else:
                [meta_data] = meta_data
                table = ExcelManager().set_active_sheet(root + "\\" + meta_data['File_Name'])\
                                      .read_sheet(meta_data['Initial_index'],
                                                  meta_data['Row_count'],
                                                  meta_data['Initial_col'],
                                                  len(self.headers))
                
                if meta_data['Row_count'] == 1:
                    table = [table]

                if meta_data["Bad_rows"] != '':
                    bad_indexes = [int(num) for num in meta_data["Bad_rows"].strip().split(',')]
                    table = [table[i] for i in range(len(table)) if i not in bad_indexes]

                return table, []

        # -----------------------------------------------------------------
        #                      Function's main starts here
        # -----------------------------------------------------------------
        current_tables = DataBase().get_table_Meta(self.name, self.format_name, self.card_number)
        self.table_1, self.table_2 = read_and_merge(current_tables, root=Local.INPUT_FOLDER)
        if self.flip_table_location:
            self.table_1, self.table_2 = self.table_2, self.table_1
        self.counter = len(self.table_1) + len(self.table_2)
        DataBase().set_new_trans_count(self.name, self.counter)

        if self.independent:
            # ------------------------------- Log ---------------------------------
            utils.log(f"File {self.format_name} is INDEPENDANT of its previous. Total valid transactions in it are {self.counter}", "system")
            # ---------------------------------------------------------------------
            return True

        from Parser import Parser
        sorted_name_format_dict = Parser.getInstance().get_names(self.format_name, self.associated, self.card_number)    # type: ignore
        recent_file_name, recent_file_format = get_recent_file_info(sorted_name_format_dict)
        # recent_file_name = get_last_file_name(list(name_format_dict.keys()))
        # recent_file_format = name_format_dict[recent_file_name]
        if recent_file_name is None:
            # ------------------------------- Log ---------------------------------
            utils.log(f"{self.name} has not earlier file - Nothing to clean. Total valid transactions in it are {self.counter}", "system")
            # --------------------------------------------------------------------- 
            return True

        recent_tables = DataBase().get_table_Meta(recent_file_name, recent_file_format, self.card_number)

        # recent tables are extacted from files which have been verified, therefore, located in a different root folder.
        recent_table_1, recent_table_2 = read_and_merge(recent_tables, root=Local.VERIFIED_FOLDER + "\\" + recent_file_format)

        def compare_tables(recent_table, current_table) -> list:
            """
            TODO
            """

            if recent_table is None:
                utils.log("recent_table is none, Check your code.", "error")
                return []

            if current_table is None:
                utils.log("curr_table is none, Check your code.", "error")
                return []
            
            if (self.format_name, recent_file_format) == ("BeinLeumi-Bank-Date-Range", "BeinLeumi-Bank") or\
                (recent_file_format, self.format_name) == ("BeinLeumi-Bank-Date-Range", "BeinLeumi-Bank"):
                recent_table = utils.match_BeinLeumi_headers(recent_table)

            # Some of the files have their transactions marked from bottom to top and some the other way around
            if self.flip:   # indication for the current table
                current_table = current_table[::-1]
            
            if Formats.FORMATS[recent_file_format]['flip']:
                recent_table = recent_table[::-1]
            
            i = -1
            index, row = get_row(recent_table)
            if row in current_table:
                i = current_table.index(row)
                for j in range(1, len(current_table) - i):
                    if j >= len(recent_table) or i + j >= len(current_table):
                        break
                    if recent_table[index + j] != current_table[i + j]:
                        utils.log(f"""Missmatched trasaction while cleaning the file {self.name},
             in accordance with it's previous {recent_file_name}.
             Try checking index: {index + j} in old table vs {i + j} in new table!
             The rows are:
             => {recent_table[index + j]}
             => {current_table[i + j]}

            What do you want to do?
            1 -> Difference in rows doesn't matter, continue as equal.
            2 -> Rows are different, Continue.
            3 -> Something is wrong, stop an let me debug.
            """, category="warning")
                        choise = int(input())
                        if choise == 2:
                            return []
                        elif choise == 3:
                            exit()
            if i == -1:
                return current_table
            return current_table[:i]

        self.table_1 = compare_tables(recent_table_1, self.table_1)

        if self.double_tables:
            self.table_2 = compare_tables(recent_table_2, self.table_2)

        new_transactions_count = len(self.table_1) + len(self.table_2)
        utils.log(f'File was cleaned: Out of {self.counter} Transactions, {new_transactions_count} new were found!', 'system')
        utils.log(f"Updating the the transaction count in the file to {new_transactions_count}", 'system')
        DataBase().set_new_trans_count(self.name, new_transactions_count)
        return True

    @abstractmethod
    def insert(self) -> bool:
        pass

    # @staticmethod
    # def cell(row: int, col: int, sheet: Sheet) -> Union[str, None]:
    #     '''
    #     Returns the value of the cell with indexes [row, col]
    #     '''
    #     if row >= 0 and col >= 0:
    #         return sheet[f'{chr(65 + col)}{row}'].value
    #     else:
    #         utils.log(f"Invalid indexes -> ({row}, {col})", "error")
    #         return ""

    def get_info(self) -> Tuple[str, str]:
        return self.name, self.format_name

    def __str__(self):
        return f"\t -> GenericFileClass"
