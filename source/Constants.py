import json


class Settings:
    DEBUG = False
    SYSTEM = True
    WARNING = True
    LAPTOP = False


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

    GAS_GRAPH = "C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/Gas_Stats.png"
    GAS_MONTHLY = "C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/Gas_monthly.png"
    GENERAL_INFO = "C:/Users/ofeks/OneDrive/Work/Projects/Personal/BankProject/General_info.png"
    
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
