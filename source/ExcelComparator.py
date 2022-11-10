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

def get_date(str):
    import re

    txt = "The rain in Spain"
    return re.search("\w{1,2}_\w{1,2}_\w{4}", str).group()

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

def get_row(table):
    for i, row in enumerate(table):
        if row[8] == "  * תנועות היום":
            pass
        else:
            return i, row
        
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
    index, row = get_row(old_table)
    if row in new_table:
        i = new_table.index(row)
        for j in range(1, len(new_table) - i):
            if  j>= len(old_table) or i + j >= len(new_table):
                break
            if old_table[index + j] != new_table[i + j]:
                return []
    return new_table[:i]


def main():
    file_names = []
    for file in listdir("C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/Inputs"):
        if isfile(join("C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/Inputs", file)) and file.endswith(".xls"):
            file_names.append(file)
    print(file_names)
    for n in file_names:
        print(get_date(n))
    
    date_lst = [get_date(name) for name in file_names]
    print(sorted(date_lst))
    
    old_file = {"name": file_names[3],
                "initial_row": 13 - 1,
                "trans_count": 40,
                "col_count": 9}
    new_file = {"name": file_names[2],
                "initial_row": 13 - 1,
                "trans_count": 40,
                "col_count": 9}
    table = compare_excel(old_file, new_file)
    for line, row in enumerate(table):
        print(f"{1+line}: {row}\n")


main()
