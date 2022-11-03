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


def compare_excel(file_name1: str, file_name2: str, start: int = 1, max_rows: int = 100):
    """
    file_name1 will be the new excel
    file_name2 will be the old excel
    """

    sheet1 = read_sheet(file_name1)
    sheet2 = read_sheet(file_name2)

    test = sheet1['A7:K7'].value

    lst = []
    for offset in range(0, max_rows):
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

    return chosen_offset


def main():
    file_names = []
    for file in listdir("C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/Inputs"):
        if isfile(join("C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/Inputs", file)) and file.endswith(".xls"):
            file_names.append(file)
    print(file_names)

    f1 = file_names[1]
    f2 = file_names[0]
    # print(f'offset: {compare_excel(f1, f2, 13, 50)}')
    # print(f'offset: {compare_excel(f1, f2, 11, 35)}')


main()
