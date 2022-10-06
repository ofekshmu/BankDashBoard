import xlwings as xw
from os import listdir
from os.path import isfile, join
from config import local, Messaging, personal


class Parser:

    def __init__(self):
        mypath = local.XLSX_PATH

        files = []
        for f in listdir(local.XLSX_PATH):
            if isfile(join(mypath, f)) and f.endswith(local.EXTENSION):
                files.append(f)

        if Messaging.SYSTEM:
            print(f'SYSTEM: found {len(files)} in {local.XLSX_PATH} ending with {local.EXTENSION}.')

        file_name = files[0]
        if Messaging.DEBUG:
            print(f'DEBUG: reading file ->\n\t{file_name}')
        wb = xw.Book(join(mypath, file_name))
        sheet = wb.sheets[0]

        if sheet['B2'].value != personal.BANK_ACC:
            if Messaging.SYSTEM:
                print(f'SYSTEM: Bank Account number does not match!')
            return False
        print('check complete')
