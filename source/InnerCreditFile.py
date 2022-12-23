from File import File
from Constants import log
from database import DataBase
from typing import Union

class InnerCreditFile(File):

    def __init__(self,
                 name: str,
                 date_loc: str,
                 bank_num_loc: str,
                 headers,
                 initial_row: int,
                 table_skip: int):
        super().__init__(name, bank_num_loc, initial_row, headers)
        self.date_loc = date_loc
        self.counter = 0
        self.data = None

    def parse(self) -> bool:
        '''
        The parse function for InnerCreditFile updates the following fields:
        self.counter1: number of transactions in the first table
        self.counter2: number of transaction in the second table
        self.data: table1 and table2 data in a 2d array
        self.date: the date specified in the file
        '''
        COL_COUNT = len(self.headers)
        
        self.data_dict = {}
        none_counter = 4
        row_index = self.initial_row + 1  # The first data row

        table_row_counter = 0
        total_counter = 0
        initial_table_index = row_index

        curr_pos = File.cell(row_index, 0, self.sheet)
        next_pos = File.cell(row_index + 1, 0, self.sheet)

        while none_counter > 0:

            if curr_pos is None or not curr_pos.isdigit():
                none_counter -= 1

                if next_pos is not None and \
                   next_pos.isdigit():
                    initial_table_index = row_index + 1
            else:
                table_row_counter += 1
                total_counter += 1

                row = self.sheet[row_index - 1: row_index, 0: COL_COUNT].value
                if curr_pos in self.data_dict.keys():
                    self.data_dict[curr_pos] += [row]
                else:
                    self.data_dict[curr_pos] = [row]

                if next_pos is None or \
                   not next_pos.isdigit() or \
                   (next_pos.isdigit() and curr_pos.isdigit() and curr_pos != next_pos):
                    DataBase().insert_table_meta_data(self.name,
                                                      initial_table_index,
                                                      table_row_counter)
                    table_row_counter = 0
                    initial_table_index = row_index + 1

            row_index += 1
            curr_pos = next_pos
            next_pos = File.cell(row_index + 1, 0, self.sheet)


        self.date = self.sheet[self.date_loc].value


        # -------------------------------------------------

        return True

    def clean(self):
        from Parser import Parser
        self.sorted_names = Parser.getInstance().get_names(InnerCreditFile)

        # TODO: This code is duplicated from the File class, need to improve this!
        def get_last_file_name() -> Union[str, None]:
            """
            Function receives the date of the current file specified in its name
            and returns the name of the most recent file of the same type, in the
            input folder
            """
            idx = self.sorted_names.index(self.name)
            if idx == 0:
                return None
            return self.sorted_names[idx - 1]

        def compare_excel(old_file: dict, new_file: dict):
            """
            file_name1 will be the new excel
            file_name2 will be the old excel
            """

            old_sheet = read_sheet(old_file["name"])
            new_sheet = read_sheet(new_file["name"])
            old_table = old_sheet[old_file["initial_row"]: old_file["initial_row"] + old_file["trans_count"], 0: old_file["col_count"]].value
            new_table = new_sheet[new_file["initial_row"]: new_file["initial_row"] + new_file["trans_count"], 0: new_file["col_count"]].value

            i = -1
            index, row = get_row(old_table)
            if row in new_table:
                i = new_table.index(row)
                for j in range(1, len(new_table) - i):
                    if j >= len(old_table) or i + j >= len(new_table):
                        break
                    if old_table[index + j] != new_table[i + j]:
                        return []
            if i == -1:
                return new_table
            return new_table[:i]
      
        old_file_name = get_last_file_name()
        if old_file_name is None:
            log(f"{self.name} has not earlier file - Nothing to clean", "system")
            return True

        old_trans_count = DataBase().total_transactions(old_file_name)
        if not old_trans_count:
            log(f"There is a problem retriving transactions for {old_file_name}", "error")
        
        old_table_stats = DataBase().get_table_stats(old_file_name)
        cleaned = []
        for idx, row_id in enumerate(old_table_stats, start=1):
            if idx != -1:  # Table exists
                old_table_i = {"name": old_file_name,
                            "initial_row": row_id - 1,
                            "trans_count": old_trans_count,
                            "col_count": len(self.headers)}
                new_table_i = {"name": self.name,
                            "initial_row": self.table_stats[idx] - 1,
                            "trans_count": self.counter,
                            "col_count": len(self.headers)}
                # The current problem is that each table requires its length and i only have the length of the totals transactions
                cleaned += compare_excel(old_table_i, new_table_i)
        log(f'Out of {len(self.data)} Transactions, {len(cleaned)} new were found!', 'system')
        self.new_trans_count = len(cleaned)
        self.data = cleaned
        return True

    def insert(self):
        """

        """
        def date_conversion(str):
            import re
            from datetime import datetime
            if isinstance(str, datetime):
                return str
            pattern = "\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}-\d{1,2}-\d{4}"
            str = re.search(pattern, str).group()
            if len(str.split('/')[-1]) == 2:
                str = str[:-2] + "20" + str[-2:]
            if "/" in str:
                return datetime.strptime(str, "%d/%m/%Y")
            else:
                return datetime.strptime(str, "%d-%m-%Y")


        total = []
        for v in self.data_dict.values():
            total += v

        DataBase().insert_file(self.name,
                               self.date,
                               "Auto Insertion",
                               "EDIT THIS",
                               len(total),
                               self.initial_row,
                               self.table_stats[2],
                               self.table_stats[3],
                               self.table_stats[4])

        counter = 0
        for row in total:
            counter += 1
            DataBase().insert_transaction(row[0], date_conversion(row[1]), row[2], -row[3], row[7], row[-1], self.name)
        return True

    def __str__(self):
        return f"\t -> InnerCreditFile"
