import json


class Settings:
    DEBUG = True
    SYSTEM = True
    WARNING = True
    LAPTOP = True


def log(msg: str, category: str):
    match category:
        case 'debug':
            if Settings.DEBUG:
                print(f'->>>>>> [DEBUG]: {msg}\n{"-"*30}\n')
        case 'system':
            if Settings.SYSTEM:
                print(f'-> [SYSTEM]: {msg}')
        case 'error':
            print(f"\n\t\tX[ERROR]X\n{25*'-'}\n: {msg}\n")
            raise ValueError("\nBreaking code...")
        case other:
            raise ValueError('Insert either system/debug')


class Local:
    '''
    Include all local enviroment related valriables
    '''
    if Settings.LAPTOP:
        XLSX_PATH = 'C:/Users/Ofek Shmuel/OneDrive/Temporary/BankProject/Inputs'
        Personal_PATH = 'C:/Users/Ofek Shmuel/OneDrive/Temporary/BankProject/personal information/personal_config.json'
    else:
        XLSX_PATH = 'C:/Users/ofeks/OneDrive/Temporary/BankProject/Inputs'
        Personal_PATH = 'C:/Users/ofeks/OneDrive/Temporary/BankProject/personal information/personal_config.json'
    EXTENSION = '.xls'


class Personal:
    '''
    All constants in this class are taken from the personal_config.json
    which is only avaliable in the local repository.
    '''
    BANK_ACC = json.load(open(Local.Personal_PATH, encoding='utf-8'))['bank_account']
    BANK_ACC_VisaFile = json.load(open(Local.Personal_PATH, encoding='utf-8'))['bank_account_visa_file']


class InnerCredit:

    SUB_STRING = "לאומי-פירוט העסקאות בכרטיסי האשראי"
    DATE_LOC = 'B5'
    BANK_NUM_LOC = 'B3'
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

    INITIAL_ROW = 10  # This is the row with the table titles
    TABLE_SKIP = 3  # Number of rows between trasnactions


class OuterCredit:
    SUB_STRING = "transaction-details_export"
    DATE = 'B3'  # This isn't the date of the xlsx creation.
    HEADERS = ["תאריך עסקה",
               "שם בית העסק",
               "קטגוריה",
               "4 ספרות אחרונות של כרטיס האשראי",
               "סוג עסקה",
               "סכום חיוב",
               "מטבע חיוב",
               "סכום עסקה",
               "מטבע עסקה",
               "תאריך חיוב",
               "הערות",
               "הערות",
               "תיוגים",
               "מועדון הנחות",
               "מפתח דיסקונט",
               "אופן ביצוע העסקה",
               "שער המרה ממטבע מקור/התחשבנות לש\"ח"]

    INITIAL_ROW = 4
    TABLE_SKIP = 0


class BankTransactions:
    SUB_STRING = "תנועות בחשבון"
    DATE = "A3"
    BANK_NUM_LOC = "A2"
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
