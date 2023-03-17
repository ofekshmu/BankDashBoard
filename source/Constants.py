import json
from msilib.schema import Error
from src_utils.utils import utils

class Settings:
    DEBUG = False
    SYSTEM = True
    WARNING = True
    LAPTOP = False


def log(msg: str, category: str = "", e: str = "\n"):

    log_st = ""
    match category:
        case 'debug':
            if Settings.DEBUG:
                log_st += f"[DEBUG]: {msg}"
        case 'system':
            if Settings.SYSTEM:
                log_st += f"[SYSTEM]: {msg}"
        case 'error':
            log_st += f"{70*'-'}\n[ERROR]: {msg}{70*'-'}\n"
        case 'db':
            log_st += f"[DataBase]: {msg}"
        case '':
            log_st += f'{msg}'
        case 'warning':
            log_st += f"<[WARNING]>: {msg}"
            
        case other:
            log(msg="Key error in function 'temp'", category='error')

    if category == "error":
        raise ValueError("\nBreaking code...")
    f = open("Log_file.txt", 'a', encoding="utf-8")
    f.write(log_st + "\n")
    f.close()
    print(log_st, end=e)


def name_he(name: str):
    try:
        i = name[::-1].index(' ')
        j = len(name) - i
        return name[:j][::-1] + " " + name[j:]
    except ValueError:
        return name


class Local:
    '''
    Include all local enviroment related valriables
    '''
    if Settings.LAPTOP:
        XLSX_PATH = 'C:/Users/Ofek Shmuel/OneDrive/Work/Projects/Personal/BankProject/Inputs'
        Personal_PATH = 'C:/Users/Ofek Shmuel/OneDrive/Work/Projects/Personal/BankProject/personal information/personal_config.json'
    else:
        XLSX_PATH = 'C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/Inputs'
        # XLSX_PATH = 'C:/Users/ofeks/Desktop/excel'
        Personal_PATH = 'C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/personal information/personal_config.json'
    EXTENSION_1 = '.xls'
    EXTENSION_2 = '.xlsx'


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
    HEADERS = ["תאריך עסקה",
               "שם בית העסק",
               "קטגוריה",
               "4 ספרות אחרונות של כרטיס האשראי",
               "סוג עסקה",
               "סכום חיוב",
               "מטבע חיוב",
               "סכום עסקה מקורי",
               "מטבע עסקה מקורי",
               "תאריך חיוב",
               "הערות",
               "תיוגים",
               "מועדון הנחות",
               "מפתח דיסקונט",
               "אופן ביצוע ההעסקה",
               "שער המרה ממטבע מקור/התחשבנות לש\"ח"]

    CARD_CELL = 'A2'
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
