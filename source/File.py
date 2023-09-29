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

        self.table_1 = []
        self.table_2 = []

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
            utils.log(f"Headers Do not match... Please check the file, format and/or code.", "system")
            return False
        else:
            utils.log("Initial headers match!", "system")

        if self.double_tables:
            row_idx = self.header_row_idx + 1
            col_idx = self.header_col_idx
            utils.log("col idx is not being checked for errors...File header valdiation", "warning")
            extracted_secondary_headers = utils.read_sheet(self.name, row_idx, 1, col_idx, len(self.secondary_headers))
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
                extracted_secondary_headers = utils.read_sheet(self.name, row_idx, 1, col_idx, len(self.secondary_headers))
        else:
            return True
        # This variables will determine the tables read in the "parse" function

        self.double_tables = False
        utils.log("Second table headers do not match...", "system")
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
                self.format_name == "Leumi-Card6744" or \
                self.format_name == "Leumi-Bank":
            self.counter += 1

        initial_index = self.header_row_idx + 1     # This is the index of the first DATA row, not headers.
        DataBase().insert_table_meta_data(source_file_name=self.name,
                                          initial_index=initial_index,
                                          initial_col=col,
                                          row_count=self.counter,
                                          bad_rows="")
        utils.log(f"Meta data saved for initial table:\n\
                    data row index:\t{initial_index}\n\
                    initial col index:\t{col}\n\
                    number of rows:\t{self.counter}", "system")
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
            counter = 0
            row_idx = self.secondary_headers_row_idx + 1
            col_idx = self.header_col_idx
            entire_row = utils.read_sheet(self.name, row_idx, 1, col_idx, len(self.secondary_headers))
            cc_end = entire_row[0]
            if is_bad_value(entire_row):
                bad_indexes.append(row_idx)
                cc_end = "Bad value"
            while cc_end is not None:
                counter += 1
                row_idx += 1
                entire_row = utils.read_sheet(self.name, row_idx, 1, col_idx, len(self.secondary_headers))
                cc_end = entire_row[0]
                if is_bad_value(entire_row):
                    bad_indexes.append(row_idx - self.secondary_headers_row_idx - 1)    # Get the index relative to the header row
                    cc_end = "Bad value"

            bad_indexes = ', '.join([str(i) for i in bad_indexes])

            initial_index = self.secondary_headers_row_idx + 1
            DataBase().insert_table_meta_data(self.name,
                                              self.secondary_headers_row_idx + 1,
                                              self.header_col_idx,
                                              counter,
                                              bad_indexes)

            utils.log(f'Meta data saved for secondary table:\n\
                    data row index:\t{initial_index}\n\
                    initial col index:\t{col}\n\
                    number of rows:\t{counter}\n\
                    Bad rows:\t\t{bad_indexes}\n\
                    valid rows:\t\t{counter - len(bad_indexes.split(","))}', 'system')

        return True

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

        def get_row(table):
            for i, row in enumerate(table):
                if len(row) < 9:
                    # this is an if stament sutied for a specific case of isra-card
                    return i, row
                if row[8] == "  * תנועות היום":
                    pass
                else:
                    return i, row

        def read_and_merge(meta_data: list[dict]):
            if self.double_tables:
                [meta_0, meta_1] = meta_data
                table_0 = utils.read_sheet(meta_0['source_file'],
                                           meta_0['Initial_index'],
                                           meta_0['Row_count'],
                                           meta_0['Initial_col'],
                                           len(self.headers))
                table_1 = utils.read_sheet(meta_1['source_file'],
                                           meta_1['Initial_index'],
                                           meta_1['Row_count'],
                                           meta_1['Initial_col'],
                                           len(self.secondary_headers))
                # This row removes the bas indexes from the second table according to the meta data
                # indexes are in accordance to the first row of the table (not the excel numbering)
                # first table is not being checked for bad indexes.
                bad_indexes = [int(num) for num in meta_1["Bad_rows"].strip().split(',')]
                table_1 = [table_1[i] for i in range(len(table_1)) if i not in bad_indexes]
                return table_0, table_1
            else:
                [meta_data] = meta_data
                return utils.read_sheet(meta_data['source_file'],
                                        meta_data['Initial_index'],
                                        meta_data['Row_count'],
                                        meta_data['Initial_col'],
                                        len(self.headers)), []

        # -----------------------------------------------------------------
        #                      Function's main starts here
        # -----------------------------------------------------------------
        current_tables = DataBase().get_table_Meta(self.name)
        self.table_1, self.table_2 = read_and_merge(current_tables)
        self.counter = len(self.table_1) + len(self.table_2)
        DataBase().set_new_trans_count(self.name, self.counter)

        if self.independent:
            # ------------------------------- Log ---------------------------------
            utils.log(f"File {self.format_name} is INDEPENDANT of its previous. Total valid transactions in it are {self.counter}", "system")
            # ---------------------------------------------------------------------
            return True

        from Parser import Parser
        sorted_names = Parser.getInstance().get_names(self.format_name)    # type: ignore
        recent_file_name = get_last_file_name(sorted_names)
        if recent_file_name is None:
            # ------------------------------- Log ---------------------------------
            utils.log(f"{self.name} has not earlier file - Nothing to clean. Total valid transactions in it are {self.counter}", "system")
            # ---------------------------------------------------------------------
            return True

        recent_tables = DataBase().get_table_Meta(recent_file_name)
        recent_table_1, recent_table_2 = read_and_merge(recent_tables)

        def compare_tables(recent_table, current_table) -> list:
            """
            """

            if recent_table is None:
                utils.log("recent_table is none, Check your code.", "error")
                return []

            if current_table is None:
                utils.log("curr_table is none, Check your code.", "error")
                return []

            # Some of the files have their transactions marked from bottom to top and some the other way around
            if flip:
                utils.log("Need to figure out a solution for one transaction tables","error")
                # if recent_row_count == 1:
                #     recent_table = [recent_table]
                # if curr_row_count == 1:
                #     curr_table = [curr_table]

                recent_table = recent_table[::-1]
                current_table = current_table[::-1]

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
