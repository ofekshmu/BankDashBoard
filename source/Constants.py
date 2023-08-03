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

    GAS_GRAPH = "C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/Outputs/Gas_info.png"
    GAS_MONTHLY = "C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/Outputs/Gas_monthly.png"
    GENERAL_INFO = "C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/Outputs/General_info.png"
    CARD_DIST_PIE = "C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/Outputs/Card_Distribution.png"

    UPDATE_FOLDER = "to_update"

    # Validation
    CHARGE_DAY = 2


class Personal:
    '''
    All constants in this class are taken from the personal_config.json
    which is only avaliable in the local repository.
    '''
    BANK_ACC = json.load(open(Local.PERSONAL_CONFIG, encoding='utf-8'))['bank_account']
    BANK_ACC_VisaFile = json.load(open(Local.PERSONAL_CONFIG, encoding='utf-8'))['bank_account_visa_file']

