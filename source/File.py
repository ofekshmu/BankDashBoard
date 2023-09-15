from abc import abstractmethod
from Constants import Local, Personal
from src_utils.utils import utils
import xlwings as xw
from xlwings import Sheet
from os.path import join
from typing import Union
from database import DataBase


class File:
    def __init__(self, name: str, format_info: dict):
        '''
        Read a work book and store an active sheet in the self.sheet.
        File is read from local.XLSX_PATH.
        A File object will be rturned upon successful read.

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

        # This value will determine the index of the secondary headers, if exists
        # The value is updated in the validate function
        self.secondary_headers_row_idx = -1

        self.data = []

        try:
            wb = xw.Book(join(Local.INPUT_FOLDER, self.name))
            self.sheet = wb.sheets[0]
        except Exception as e:
            utils.log(f"Original error: {str(e)}\nFile read Failed!\nFile name: {self.name}\
                In File -> line 39\nMake sure the file is not open.", 'error')

    def load(self) -> bool:
        '''
        Read a work book and store an active sheet in the self.sheet.
        File is read from local.XLSX_PATH, and true is returned upon succesful read,
        False otherwise.

        Parameters
        ----------
        file_name: a string indicating the name of the file
        '''
        try:
            wb = xw.Book(join(Local.INPUT_FOLDER, self.name))
            self.sheet = wb.sheets[0]
            return True
        except Exception as e:
            utils.log(str(e), category='debug')
            return False

    @abstractmethod
    def validate_bank_number(self) -> bool:
        '''
        The function validates the Bank account specified in the file.
        The cell indicating the number is specified trough the Constants.py
        '''
        if self.bank_num_loc is None:
            return True
        value = self.sheet[self.bank_num_loc].value
        if Personal.BANK_ACC in value:
            return True
        return False

    def validate_headers(self) -> bool:
        '''
        The function validates the table headers in the file.
        The values of the headers and the initial row are given in the Constants.py.
        '''
        # Looks for the headers in a @err area of the given estimated
        err = 2
        temp = self.header_row_idx - err
        lower_bound = 1 if temp < 1 else temp
        for row in range(lower_bound, self.header_row_idx + err):
            for i in range(0, 3):   # error in col selection TODO: improve impl
                valid = True
                col = i
                for name in self.headers:
                    utils.log(f'(FILE/Validate_headers) row number = {row}, col = {col}, name = {name[::-1]}', 'debug')
                    value = utils.cell(row, col, self.sheet)
                    if not value == name:
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
        
        if not valid:
            return False
        
        if self.double_tables:
            row_idx = self.header_row_idx + 1
            col_idx = self.header_col_idx
            utils.log("col idx is not being checked for errors...File header valdiation", "warning")
            extracted_secondary_headers = utils.read_sheet(self.name, row_idx, 1, col_idx, len(self.secondary_headers))
            tries_left = 1_000
            while tries_left:
                if extracted_secondary_headers == self.secondary_headers:
                    utils.log("Secondary headers match!", "system")
                    self.secondary_headers_row_idx = row_idx
                    return True
                row_idx += 1
                tries_left -= 1
                extracted_secondary_headers = utils.read_sheet(self.name, row_idx, 1, col_idx, len(self.secondary_headers))
        else:
            return True
        # This variables will determine the tables read in the "parse" function

        self.double_tables = False
        return False

    @abstractmethod
    def parse(self) -> bool:
        """
        Function responsibility is the complete parse of the data file.
        Currently, 'BankTransactionFile' and 'OuterCreditFile' are using this implementation.
        'Inner credit file is using a different one becuase of the complexity.
        """
        counter = 0
        row = self.header_row_idx + 1
        col = self.header_col_idx

        cc_end = File.cell(row, col, self.sheet)

        while cc_end is not None and cc_end != "עסקאות בחו˝ל":
            counter += 1
            row += 1
            cc_end = File.cell(row, col, self.sheet)

        self.counter = counter - 1

        if self.format_name == "American-Express" or \
                self.format_name == "Leumi-Card6744":
            self.counter += 1
        # Inset the meta data of the file to db for future reference
        DataBase().insert_table_meta_data(self.name,
                                          self.header_row_idx + 1,
                                          col,
                                          self.counter,
                                          "")

        utils.log("The parse function for catd 2922 is not generic - (-1) is added to ignore last row", "warning")

        # ------------------------------------------------------------
        #                  Secondary header parsing
        # ------------------------------------------------------------
        def is_bad_value(entire_row) -> bool:
            """
            Bad values are predetermined and are not included in the final parsed table.
            Bad values are used to ignore tables rows that do not represent transactions.
            These are identified using....
            """
            if entire_row[2] == "TOTAL FOR DATE":
                return True
            return False

        if self.double_tables:
            bad_indexes = []
            row_idx = self.secondary_headers_row_idx
            col_idx = self.header_col_idx
            cc_end = File.cell(row_idx, col_idx, self.sheet)
            entire_row = utils.read_sheet(self.name, row_idx, 1, col_idx, len(self.secondary_headers))
            cc_end = entire_row[0]
            while cc_end is not None:
                if is_bad_value(entire_row):
                    bad_indexes.append(row_idx)
                counter += 1
                row_idx += 1
                cc_end = File.cell(row, col, self.sheet)

            bad_indexes = ', '.join([str(i) for i in bad_indexes])

            DataBase().insert_table_meta_data(self.name,
                                              self.header_row_idx + 1,
                                              col,
                                              self.counter,
                                              bad_indexes)

        # # This part might need changing from here on

        # COL_COUNT = len(self.headers)
        # table = self.sheet[self.header_row_idx: self.header_row_idx + self.counter, col: COL_COUNT + col].value

        # # Happens if table is empty (No transactions)
        # if table is None:
        #     table = []
        # # To stay consistent with the data structure
        # elif counter == 1:
        #     table = [table]

        # self.data = table

    def clean(self, flip: bool = False) -> bool:
        """
        Function will clean the read data.
        Given a table of transactions, it will change the table to contain only new
        ones which did not appear before.
        """

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
            return sorted_names[idx - 1]

        def read_sheet(file_name: str) -> Sheet:
            wb = xw.Book(join(Local.INPUT_FOLDER, file_name))
            return wb.sheets[0]

        def get_row(table):
            for i, row in enumerate(table):
                if len(row) < 9:
                    # this is an if stament sutied for a specific case of isra-card
                    return i, row
                if row[8] == "  * תנועות היום":
                    pass
                else:
                    return i, row

        # -----------------------------------------------------------------
        #                      Function main starts here
        # -----------------------------------------------------------------
        if self.independent:
            utils.log(f"File of format {self.format_name} is independent of other files and is not being cleaned.", "system")
            # TODO: what happens in a case of two tables? is the counter being summed?
            DataBase().set_new_trans_count(self.name, self.counter)
            return True

        from Parser import Parser
        # TODO: can i get rid of the self in self.sorted_names
        sorted_names = Parser.getInstance().get_names(self.format_name)    # type: ignore

        recent_file_name = get_last_file_name(sorted_names)
        if recent_file_name is None:
            DataBase().set_new_trans_count(self.name, self.counter)
            utils.log(f"{self.name} has not earlier file - Nothing to clean.", "system")
            return True

        # trans_count = DataBase().total_transactions(recent_file_name)
        recent_tables = DataBase().get_table_Meta(recent_file_name)
        current_tables = DataBase().get_table_Meta(self.name)

        if self.double_tables:
            [recent_table_0_meta, recent_table_1_meta] = recent_tables
            [curr_table_0_meta, curr_table_1_meta] = current_tables
            total_transactions = recent_table_0_meta[4] + recent_table_1_meta[4] + \
                                        curr_table_0_meta[4] + curr_table_1_meta[4]
        else:   # Single table in each excel file
            recent_table_0_meta = recent_tables[0]
            curr_table_0_meta = current_tables[0]
            total_transactions = recent_table_0_meta[4] + curr_table_0_meta[4]

        # -------------------------------------------------------------------------------------------
        # I do not think this if ever accured... maybe should delete?
        # if not trans_count:
        #    utils.log(f"There is a problem retriving transactions for {recent_file_name}", "error")
        # ---------------------------------------------------------------------------------------------

        # Improved API:
        def compare_tables(recent_file_name,
                           recent_initial_row,
                           recent_initial_col,
                           recent_row_count,
                           curr_file_name,
                           curr_initial_row,
                           curr_initial_col,
                           curr_row_count,
                           headers_count) -> list:
            """
            """
            # TODO: add a sanity check for headers length...

            recent_sheet = read_sheet(recent_file_name)
            curr_sheet = read_sheet(curr_file_name)
            recent_table = recent_sheet[recent_initial_row: recent_initial_row + recent_row_count,
                                        recent_initial_col: recent_initial_col + headers_count].value
            curr_table = curr_sheet[curr_initial_row: curr_initial_row + curr_row_count,
                                    curr_initial_col: curr_initial_col + headers_count].value

            if recent_table is None:
                utils.log("recent_table is none, Check your code.", "error")
                return []

            if curr_table is None:
                utils.log("curr_table is none, Check your code.", "error")
                return []

            # Some of the files have their transactions marked from bottom to top and some the other way around
            if flip:
                if recent_row_count == 1:
                    recent_table = [recent_table]
                if curr_row_count == 1:
                    curr_table = [curr_table]

                recent_table = recent_table[::-1]
                curr_table = curr_table[::-1]

            i = -1
            index, row = get_row(recent_table)
            if row in curr_table:
                i = curr_table.index(row)
                for j in range(1, len(curr_table) - i):
                    if j >= len(recent_table) or i + j >= len(curr_table):
                        break
                    if recent_table[index + j] != curr_table[i + j]:
                        utils.log(f"""Missmatched trasaction while cleaning the file {self.name},
             in accordance with it's previous {recent_file_name}.
             Try checking index: {index + j} in old table vs {i + j} in new table!
             The rows are:
             => {recent_table[index + j]}
             => {curr_table[i + j]}

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
                return curr_table
            return curr_table[:i]

        result_table = compare_tables(recent_file_name,
                                      recent_table_0_meta[2] - 1,  # This was previously the header row, need to change,
                                      recent_table_0_meta[3],
                                      recent_table_0_meta[4],
                                      self.name,
                                      curr_table_0_meta[2] - 1,
                                      curr_table_0_meta[3],
                                      curr_table_0_meta[4],
                                      len(self.headers))

        if self.double_tables:
            result_table += compare_tables(recent_file_name,
                                           recent_table_1_meta[2] - 1,  # This was previously the header row, need to change,
                                           recent_table_1_meta[3],
                                           recent_table_1_meta[4],
                                           self.name,
                                           curr_table_1_meta[2] - 1,
                                           curr_table_1_meta[3],
                                           curr_table_1_meta[4],
                                           len(self.secondary_headers))

        utils.log(f'\t     Out of {total_transactions} Transactions, {len(result_table)} new were found!', '')
        DataBase().set_new_trans_count(self.name, len(result_table))
        self.data = ""  # TODO

        return True

    @abstractmethod
    def insert(self) -> bool:
        pass

    @staticmethod
    def cell(row: int, col: int, sheet: Sheet) -> Union[str, None]:
        '''
        Returns the value of the cell with indexes [row, col]
        '''
        if row >= 0 and col >= 0:
            return sheet[f'{chr(65 + col)}{row}'].value
        else:
            utils.log(f"Invalid indexes -> ({row}, {col})", "error")
            return ""

    def __str__(self):
        return f"\t -> GenericFileClass"
