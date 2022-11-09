import xlwings as xw
from xlwings import Sheet
from os.path import join, isfile
from os import listdir
from typing import Union


def read_sheet(file_name: str) -> Sheet:
    # try:
    wb = xw.Book(join("C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/Inputs", file_name))
    return wb.sheets[0]
    # except Exception as e:
    #     #log(str(e), category='debug')
    #     return False


def cell(row: int, col: int, sheet: Sheet) -> Union[str, None]:
    '''
    Returns the value of the cell with indexes [row, col]
    '''
    if row >= 0 and col >= 0:
        return sheet[f'{chr(65 + col)}{row}'].value
    else:
        return ""


def row(row: int, col_init: int, col_end: int, sheet: Sheet) -> Union[str, None]:
    '''
    Returns the value of the cell with indexes [row, col]
    '''
    if row >= 0:
        val = f'{chr(65 + col_init)}{row}:{chr(65 + col_end)}{row}'
        return sheet[val].value
    else:
        return ""


def compare_excel(old_file: dict, new_file: dict):
    """
    file_name1 will be the new excel
    file_name2 will be the old excel
    """

    old_sheet = read_sheet(old_file["name"])
    new_sheet = read_sheet(new_file["name"])
    x = old_sheet[0:20, 0:13].value
    old_table = old_sheet[old_file["initial_row"]: old_file["initial_row"] + old_file["trans_count"], 0: old_file["col_count"]].value
    new_table = new_sheet[new_file["initial_row"]: new_file["initial_row"] + new_file["trans_count"], 0: new_file["col_count"]].value

    lst = []
    i = -1
    row = old_table[0]
    if row in new_table:
        i = new_table.index(row)
        for j in range(1, len(new_table) - i):
            if  j>= len(old_table) or i + j >= len(new_table):
                break
            if old_table[j] != new_table[i + j]:
                return []
    return new_table[:i]


    lst = []
    for offset in range(old_table):
        rate = 0
        for i in range(0, max_rows):
            row1 = row(start + i + offset, 0, 10, sheet1)
            row2 = row(start + i, 0, 10, sheet2)

            if row1 == row2:
                rate += 1
        lst.append(rate/max_rows)

    # get the offset with the gihest rate
    # find max value in list
    highest_rate = max(lst)
    print(f'The highest rate: {highest_rate}')
    # find index of max value in list
    chosen_offset = lst.index(highest_rate)

    table = sheet1[start: start + chosen_offset, 0: 10].value
    # Happens if table is empty (No transactions)
    if table is None:
        table = []
    # To stay consistent with the data structure
    elif chosen_offset == 1:
        table = [table]

    print(table)

    return chosen_offset


def main():
    file_names = []
    for file in listdir("C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/Inputs"):
        if isfile(join("C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/Inputs", file)) and file.endswith(".xls"):
            file_names.append(file)
    print(file_names)

    f1 = file_names[3]
    f2 = file_names[2]
    # print(f'offset: {compare_excel(f1, f2, 13, 50)}')

    old_file = {"name": f1,
                "initial_row": 13,
                "trans_count": 40,
                "col_count": 9}
    new_file = {"name": f1,
                "initial_row": 13,
                "trans_count": 42,
                "col_count": 9}
    print(f'offset: {compare_excel(old_file, new_file)}')


main()
