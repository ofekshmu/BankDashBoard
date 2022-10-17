import json


def log(msg: str, category: str):
    match category:
        case 'debug':
            if Messaging.DEBUG:
                print(f'\n{"-"*30}\n[DEBUG]: {msg}\n{"-"*30}\n')
        case 'system':
            if Messaging.SYSTEM:
                print(f'-> [SYSTEM]: {msg}')
        case 'error':
            print(f'! -> [ERROR]: {msg}')
        case other:
            raise ValueError('Insert either system/debug')


class local:
    '''
    Include all local enviroment related valriables
    '''
    XLSX_PATH = 'C:/Users/ofeks/OneDrive/Temporary/BankProject/Inputs'
    Personal_PATH = 'C:/Users/ofeks/OneDrive/Temporary/BankProject/personal information/personal_config.json'
    EXTENSION = '.xls'


class personal:
    '''
    All constants in this class are taken from the personal_config.json
    which is only avaliable in the local repository.
    '''
    BANK_ACC = json.load(open(local.Personal_PATH, encoding='utf-8'))['bank_account']
    BANK_ACC_VisaFile = json.load(open(local.Personal_PATH, encoding='utf-8'))['bank_account_visa_file']


class Messaging:
    DEBUG = False
    SYSTEM = True


class creditFile:
    HEADERS = ["מספר הכרטיס",
               "תאריך העסקה",
               "שם בית העסק",
               "סכום העסקה",
               "מטבע העסקה",
               "סכום החיוב",
               "מטבע חיוב העסקה",
               "סוג העסקה",
               "פרטים",
               "תאריך החיוב"]

    COL_COUNT = len(HEADERS)
    DATE = 'B5'
    BANK_ACC = 'B3'
    HEADER_ROW = 10
    TABLE_SKIP = 3               # 3 rows different between data sections


class MonthlyFile:
    HEADERS = ['כרטיס',
               'סכום החיוב',
               'תאריך החיוב']
    COL_COUNT = len(HEADERS)
    DATE = 'B3'
    BANK_ACC = 'B2'
    HEADER_ROW = 9
    TABLE_SKIP = 3


class VisaFile:
    HEADERS = ['תאריך',
               'תאריך ערך',
               'תיאור',
               'אסמכתא',
               'בחובה',
               'בזכות',
               'היתרה בש"ח',
               'תאור מורחב',
               '  הערה']

    COL_COUNT = len(HEADERS)
    DATE = 'A3'
    BANK_ACC = 'A2'
    HEADER_ROW = 12
    TABLE_SKIP = 0
