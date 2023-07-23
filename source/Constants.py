########################################################################
#                             CONFIG FILE
#
#  Mind that on WINDOWS OS, all slashes are as follows: /
#
########################################################################

import json
from enum import Enum


class Settings:
    DEBUG = False
    SYSTEM = True
    WARNING = True
    LAPTOP = False


class Method(Enum):
    FILE_NAME = 1
    CELL = 2
    HEADERS = 3
    NONE = 4


class Sortion(Enum):
    BY_NAME_SERIAL = 1
    BY_NAME_DATE = 2


class Local:
    '''
    Include all local enviroment related valriables
    '''
    DB_NAME = "TEST_DataBase"

    INPUT_FOLDER = 'Inputs_testing'
    PERSONAL_CONFIG = 'Yuvals personal information/personal_config.json'

    CATE_JSON_PATH = 'personal information\categories.json'
    EXTENSION_1 = '.xls'
    EXTENSION_2 = '.csv'
    EXTENSION_3 = ''  # Add another extension option here if needed or leave as an empty string.

    GAS_GRAPH = "C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/Gas_Stats.png"
    GAS_MONTHLY = "C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/Gas_monthly.png"
    GENERAL_INFO = "C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/General_info.png"

    # Validation
    CHARGE_DAY = 2


class Personal:
    '''
    All constants in this class are taken from the personal_config.json
    which is only avaliable in the local repository.
    '''
    BANK_ACC = json.load(open(Local.PERSONAL_CONFIG, encoding='utf-8'))['bank_account']
    BANK_ACC_VisaFile = json.load(open(Local.PERSONAL_CONFIG, encoding='utf-8'))['bank_account_visa_file']


class File:
    pass


class InnerCredit(File):

    FORMAT_METHOD = Method.HEADERS
    INFO = ""

    SORTION = Sortion.BY_NAME_SERIAL

    SUB_STRING = "לאומי-פירוט העסקאות בכרטיסי האשראי"
    DATE_LOC = None
    BANK_NUM_LOC = None
    HEADERS = ["תאריך עסקה",
               "שם  העסק",
               "סכום עסקה",
               "סכום חיוב",
               "פירוט"]

    INITIAL_ROW = 6  # This is the row with the table titles
    INITIAL_COL = 1  # This is the starting col of the table
    TABLE_SKIP = 0  # Number of empty rows between trasnactions


class OuterCredit(File):

    FORMAT_METHOD = Method.FILE_NAME
    SUB_STRING = "Export"
    INFO = ("B2", "TEST")

    SORTION = Sortion.BY_NAME_DATE

    HEADERS = ["תאריך רכישה",
               "שם בית עסק",
               "סכום עסקה",
               "מטבע מקור",
               "סכום חיוב",
               "מטבע לחיוב",
               "מספר שובר",
               "פירוט נוסף"]

    CARD_CELL = 'A4'
    INITIAL_ROW = 6
    TABLE_SKIP = 0


class BankTransactions(File):

    FORMAT_METHOD = Method.FILE_NAME
    INFO = ""
    
    SORTION = Sortion.BY_NAME_DATE

    SUB_STRING = "תנועות בחשבון"
    DATE = None
    BANK_NUM_LOC = None
    HEADERS = ['תאריך',
               'תאריך ערך',
               'תיאור',
               'אסמכתא',
               'בחובה',
               'בזכות',
               'היתרה בש"ח',
               'תאור מורחב',
               '  הערה']

    INITIAL_ROW = 12
    TABLE_SKIP = 0
